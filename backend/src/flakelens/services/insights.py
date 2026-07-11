"""Read-side analytics: incidents (failure clustering), regression alerts
(trend detection), and a project health grade. All pure/DB-read — no LLM."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from flakelens.models import Run, TestCase, TestResult
from flakelens.services.crew import build_incidents

INCIDENT_WINDOW_HOURS = 24 * 7
REGRESSION_SLOWDOWN = 1.5  # 50% slower than its own average = flagged


def recent_failures(db: Session, project_id: int, hours: int = INCIDENT_WINDOW_HOURS) -> list[tuple]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    run_ids = list(db.scalars(
        select(Run.id).where(
            Run.project_id == project_id, Run.status == "completed",
            Run.started_at >= cutoff.replace(tzinfo=None),
        )
    ).all())
    if not run_ids:
        return []
    return db.execute(
        select(TestResult, TestCase)
        .join(TestCase, TestCase.id == TestResult.test_case_id)
        .where(TestResult.run_id.in_(run_ids), TestResult.status.in_(("failed", "error")))
    ).all()


def project_incidents(db: Session, project_id: int) -> list[dict]:
    incidents = build_incidents(recent_failures(db, project_id))
    # Trim internal fields the crew uses; keep what a viewer needs.
    for inc in incidents:
        inc.pop("result_ids", None)
        inc.pop("case_ids", None)
    return incidents


def _latest_completed_runs(db: Session, project_id: int, limit: int) -> list[Run]:
    runs = db.scalars(
        select(Run).where(Run.project_id == project_id, Run.status == "completed")
        .order_by(Run.started_at.desc()).limit(limit)
    ).all()
    return list(reversed(runs))  # oldest -> newest


def regression_alerts(db: Session, project_id: int) -> list[dict]:
    """Trend signals a human should act on: pass-rate drop, newly-broken tests,
    and tests running much slower than their own history."""
    alerts: list[dict] = []
    runs = _latest_completed_runs(db, project_id, 10)
    if len(runs) >= 3:
        latest, prev = runs[-1], runs[-2]
        pr_latest = latest.passed / latest.total if latest.total else 1.0
        pr_prev = prev.passed / prev.total if prev.total else 1.0
        if pr_prev - pr_latest >= 0.1:
            alerts.append({
                "kind": "pass_rate_drop", "severity": "high",
                "message": f"Pass rate dropped {round((pr_prev - pr_latest) * 100)}% "
                           f"(from {round(pr_prev * 100)}% to {round(pr_latest * 100)}%) in run #{latest.id}.",
                "run_id": latest.id,
            })

    # Tests that were green last run and are now failing.
    if len(runs) >= 2:
        latest, prev = runs[-1], runs[-2]
        prev_status = dict(db.execute(
            select(TestResult.test_case_id, TestResult.status).where(TestResult.run_id == prev.id)
        ).all())
        rows = db.execute(
            select(TestResult, TestCase).join(TestCase, TestCase.id == TestResult.test_case_id)
            .where(TestResult.run_id == latest.id, TestResult.status.in_(("failed", "error")))
        ).all()
        newly = [c.node_id for r, c in rows if prev_status.get(r.test_case_id) == "passed"]
        if newly:
            alerts.append({
                "kind": "newly_failing", "severity": "high",
                "message": f"{len(newly)} test(s) newly failing vs the previous run.",
                "tests": newly[:10], "run_id": latest.id,
            })

    # Slowdowns: a case whose latest duration is much above its rolling average.
    slow = []
    cases = db.scalars(
        select(TestCase).where(TestCase.project_id == project_id, TestCase.avg_duration_ms > 200)
    ).all()
    for case in cases:
        entries = case.recent_statuses or []
        if len(entries) >= 4 and case.avg_duration_ms:
            last = entries[-1].get("d", 0)
            if last >= case.avg_duration_ms * REGRESSION_SLOWDOWN:
                slow.append({"node_id": case.node_id, "case_id": case.id,
                             "last_ms": last, "avg_ms": case.avg_duration_ms})
    slow.sort(key=lambda s: s["last_ms"] / max(1, s["avg_ms"]), reverse=True)
    if slow:
        alerts.append({
            "kind": "slowdown", "severity": "medium",
            "message": f"{len(slow)} test(s) running notably slower than their average.",
            "tests": slow[:8],
        })
    return alerts


def health_grade(db: Session, project_id: int) -> dict:
    """A single A-F project grade + the drivers behind it, in plain language."""
    runs = _latest_completed_runs(db, project_id, 10)
    flaky = db.scalar(select(func.count(TestCase.id)).where(
        TestCase.project_id == project_id, TestCase.is_flaky.is_(True))) or 0
    total_cases = db.scalar(select(func.count(TestCase.id)).where(
        TestCase.project_id == project_id)) or 0
    if not runs:
        return {"grade": "—", "score": 0, "pass_rate": None, "flaky": flaky,
                "drivers": ["No completed runs yet."]}

    latest = runs[-1]
    pass_rate = latest.passed / latest.total if latest.total else 1.0
    flaky_ratio = flaky / total_cases if total_cases else 0.0
    incident_count = len(project_incidents(db, project_id))

    # Score out of 100: pass rate dominates, flakiness + incidents subtract.
    score = pass_rate * 100
    score -= min(30, flaky_ratio * 100)
    score -= min(20, incident_count * 4)
    score = max(0, round(score))
    grade = ("A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70
             else "D" if score >= 60 else "F")

    drivers = []
    if pass_rate < 1.0:
        drivers.append(f"Latest run pass rate is {round(pass_rate * 100)}%.")
    if flaky:
        drivers.append(f"{flaky} flaky test(s) undermine trust in results.")
    if incident_count:
        drivers.append(f"{incident_count} open failure incident(s) this week.")
    if not drivers:
        drivers.append("All green — suite is healthy.")
    return {"grade": grade, "score": score, "pass_rate": round(pass_rate, 4),
            "flaky": flaky, "incidents": incident_count, "drivers": drivers}


def action_list(db: Session, project_id: int, repo_url: str | None) -> list[dict]:
    """Plain-language 'what should I do today', prioritized. Each item names the
    concern, why it matters, and the recommended action a non-expert can take."""
    actions: list[dict] = []
    incidents = project_incidents(db, project_id)
    flaky_cases = db.scalars(
        select(TestCase).where(TestCase.project_id == project_id, TestCase.is_flaky.is_(True),
                               TestCase.quarantined_at.is_(None))
        .order_by(TestCase.flake_score.desc()).limit(5)
    ).all()

    for inc in incidents[:3]:
        node = inc["node_ids"][0] if inc.get("node_ids") else "a test"
        actions.append({
            "priority": "high", "title": f"{inc['count']} failures need a look",
            "detail": f'"{node}"'
                      + (f" and {len(inc['node_ids']) - 1} more" if len(inc.get("node_ids", [])) > 1 else "")
                      + " are failing. Open it to see the AI analysis and, if it's a test bug, run SelfHeal.",
            "link": f"/tests/{inc['worst_case_id']}" if inc.get("worst_case_id") else None,
        })
    for case in flaky_cases[:2]:
        actions.append({
            "priority": "medium", "title": "Quarantine a flaky test",
            "detail": f'"{case.node_id}" fails intermittently ({round(case.flake_score * 100)}% flaky). '
                      "Quarantine it so it stops blocking CI while SelfHeal works on a fix.",
            "link": "/quarantine",
        })
    if not actions:
        actions.append({"priority": "low", "title": "Nothing urgent",
                        "detail": "Your suite is healthy. Consider writing a new test in plain English.",
                        "link": "/author"})
    return actions
