"""The nightly maintenance crew.

One pass = triage every failure since the last pass, clustered by failure
fingerprint into INCIDENTS ("14 failures, 1 broken service"), classify each
incident once with the AI analyst, then take bounded actions:

  TEST_BUG      -> launch SelfHeal on the incident's freshest failing result
  FLAKY_TIMING  -> quarantine the worst offender (if flagged flaky, not yet quarantined)
  APP_BUG / ENVIRONMENT / UNKNOWN -> report only (humans own the app)

Budgets cap AI spend per pass. The output is a morning digest (dashboard +
optional Slack webhook): what broke, why, what the crew already did about it.
"""
import os
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from flakelens.db import SessionLocal
from flakelens.models import AgentJob, CrewRun, Project, Run, TestCase, TestResult

# Per-pass budgets: bound cost and blast radius.
MAX_INCIDENTS_ANALYZED = 5
MAX_HEALS = 2
MAX_QUARANTINES = 1
DEFAULT_WINDOW_HOURS = 24

CLASSIFICATIONS = ("APP_BUG", "TEST_BUG", "FLAKY_TIMING", "ENVIRONMENT", "UNKNOWN")


# --- pure helpers (unit-tested directly) -----------------------------------

def build_incidents(rows: list[tuple]) -> list[dict]:
    """Cluster (TestResult, TestCase) pairs into incidents by failure fingerprint.

    Results without a fingerprint (e.g. flaky-in-run passes) cluster per test case.
    Incidents are ordered by blast radius (result count desc)."""
    clusters: dict[str, dict] = {}
    for result, case in rows:
        key = result.failure_fingerprint or f"case-{case.id}"
        incident = clusters.setdefault(key, {
            "fingerprint": result.failure_fingerprint,
            "error_type": result.error_type,
            "error_message": (result.error_message or "")[:300],
            "result_ids": [],
            "case_ids": set(),
            "node_ids": set(),
            "latest_result_id": result.id,
            "worst_case_id": case.id,
            "worst_flake_score": case.flake_score,
        })
        incident["result_ids"].append(result.id)
        incident["case_ids"].add(case.id)
        incident["node_ids"].add(case.node_id)
        if result.id > incident["latest_result_id"]:
            incident["latest_result_id"] = result.id
            incident["error_type"] = result.error_type
            incident["error_message"] = (result.error_message or "")[:300]
        if case.flake_score > incident["worst_flake_score"]:
            incident["worst_case_id"] = case.id
            incident["worst_flake_score"] = case.flake_score

    incidents = []
    for incident in clusters.values():
        incident["case_ids"] = sorted(incident["case_ids"])
        incident["node_ids"] = sorted(incident["node_ids"])
        incident["count"] = len(incident["result_ids"])
        incidents.append(incident)
    incidents.sort(key=lambda i: i["count"], reverse=True)
    return incidents


def parse_classification(analysis_text: str) -> str:
    """Pull the classification token out of the analyst's markdown."""
    for token in CLASSIFICATIONS:
        if re.search(rf"\b{token}\b", analysis_text or ""):
            return token
    return "UNKNOWN"


def render_digest(project_name: str, window_start, incidents: list[dict],
                  runs_seen: int, failures_seen: int) -> str:
    lines = [
        f"## FlakeLens maintenance crew — {project_name}",
        f"Window since {window_start:%b %d %H:%M} UTC: "
        f"{runs_seen} run(s), {failures_seen} failing result(s) → {len(incidents)} incident(s).",
        "",
    ]
    if not incidents:
        lines.append("All quiet. No new failures in this window. ✅")
        return "\n".join(lines)
    for index, incident in enumerate(incidents, 1):
        title = incident["node_ids"][0] if incident["node_ids"] else "unknown test"
        extra = f" (+{len(incident['node_ids']) - 1} more tests)" if len(incident["node_ids"]) > 1 else ""
        lines.append(f"### Incident {index}: {title}{extra}")
        lines.append(
            f"- {incident['count']} failure(s) · {incident.get('classification', 'UNANALYZED')}"
        )
        if incident.get("error_message"):
            lines.append(f"- Error: {incident.get('error_type')}: {incident['error_message'][:160]}")
        action = incident.get("action") or {}
        if action.get("kind"):
            outcome = action.get("status", "?")
            detail = action.get("pr_url") or action.get("branch") or ""
            lines.append(f"- Crew action: {action['kind']} → {outcome} {detail}".rstrip())
        else:
            lines.append(f"- Crew action: none ({incident.get('action_reason', 'report only')})")
        lines.append("")
    return "\n".join(lines)


# --- orchestration -----------------------------------------------------------

def post_slack(digest: str) -> bool:
    webhook = os.environ.get("FLAKELENS_SLACK_WEBHOOK")
    if not webhook:
        return False
    try:
        import httpx

        httpx.post(webhook, json={"text": digest[:39000]}, timeout=15)
        return True
    except Exception:
        return False


def execute_crew_run(crew_run_id: int) -> None:
    db = SessionLocal()
    try:
        crew = db.get(CrewRun, crew_run_id)

        def log(line: str) -> None:
            crew.log = (crew.log or "") + line + "\n"
            db.commit()

        try:
            project = db.get(Project, crew.project_id)
            crew.status = "running"
            db.commit()

            previous = db.scalar(
                select(CrewRun)
                .where(CrewRun.project_id == project.id,
                       CrewRun.status == "completed",
                       CrewRun.id != crew.id)
                .order_by(CrewRun.id.desc())
            )
            window_start = (
                previous.created_at if previous is not None
                else datetime.now(timezone.utc) - timedelta(hours=DEFAULT_WINDOW_HOURS)
            )
            if window_start.tzinfo is None:
                window_start = window_start.replace(tzinfo=timezone.utc)
            crew.window_start = window_start
            db.commit()

            runs = db.scalars(
                select(Run).where(
                    Run.project_id == project.id,
                    Run.status == "completed",
                    Run.started_at >= window_start.replace(tzinfo=None),
                )
            ).all()
            run_ids = [r.id for r in runs]
            rows = []
            if run_ids:
                rows = db.execute(
                    select(TestResult, TestCase)
                    .join(TestCase, TestCase.id == TestResult.test_case_id)
                    .where(
                        TestResult.run_id.in_(run_ids),
                        TestResult.status.in_(("failed", "error")),
                    )
                ).all()
            log(f"Window since {window_start:%Y-%m-%d %H:%M} UTC: "
                f"{len(runs)} completed run(s), {len(rows)} failing result(s).")

            incidents = build_incidents(rows)
            log(f"Clustered into {len(incidents)} incident(s).")

            ai_available = bool(os.environ.get("ANTHROPIC_API_KEY"))
            heals = quarantines = 0
            for index, incident in enumerate(incidents):
                if index >= MAX_INCIDENTS_ANALYZED or not ai_available:
                    incident["classification"] = "UNANALYZED"
                    incident["action_reason"] = (
                        "analysis budget reached" if ai_available else "no ANTHROPIC_API_KEY"
                    )
                    continue
                incident["classification"] = _classify(db, incident, log)
                heals, quarantines = _act(
                    db, project, incident, heals, quarantines, log
                )

            failures_seen = sum(i["count"] for i in incidents)
            digest = render_digest(project.name, window_start, incidents,
                                   runs_seen=len(runs), failures_seen=failures_seen)
            crew.incidents = incidents
            crew.digest = digest
            if post_slack(digest):
                log("Digest posted to Slack.")
            crew.status = "completed"
            log("Crew pass complete.")
        except Exception as exc:
            crew.status = "failed"
            crew.error = str(exc)[:2000]
            log(f"ERROR: {exc}")
        finally:
            crew.finished_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()


def _classify(db, incident: dict, log) -> str:
    from flakelens.models import TestResult
    from flakelens.services.analysis import analyze_result

    try:
        result = db.get(TestResult, incident["latest_result_id"])
        analysis = analyze_result(db, result)
        classification = parse_classification(analysis.content)
        log(f"Incident '{incident['node_ids'][0]}': classified {classification}")
        return classification
    except Exception as exc:
        log(f"Incident '{incident['node_ids'][0]}': analysis failed ({exc})")
        return "UNKNOWN"


def _act(db, project, incident: dict, heals: int, quarantines: int, log):
    from flakelens.services.autofix import execute_autofix_job
    from flakelens.services.quarantine import execute_marker_job

    classification = incident["classification"]
    if classification == "TEST_BUG" and heals < MAX_HEALS and project.repo_url:
        job = AgentJob(result_id=incident["latest_result_id"], kind="autofix")
        db.add(job)
        db.commit()
        log(f"  -> SelfHeal launched (job #{job.id})")
        execute_autofix_job(job.id)
        db.refresh(job)
        incident["action"] = {"kind": "selfheal", "job_id": job.id, "status": job.status,
                              "branch": job.branch, "pr_url": job.pr_url}
        return heals + 1, quarantines

    if classification == "FLAKY_TIMING" and quarantines < MAX_QUARANTINES and project.repo_url:
        case = db.get(TestCase, incident["worst_case_id"])
        if case is not None and case.is_flaky and case.quarantined_at is None:
            job = AgentJob(result_id=incident["latest_result_id"], kind="quarantine")
            db.add(job)
            db.commit()
            log(f"  -> Quarantine launched (job #{job.id})")
            execute_marker_job(job.id)
            db.refresh(job)
            incident["action"] = {"kind": "quarantine", "job_id": job.id, "status": job.status,
                                  "branch": job.branch, "pr_url": job.pr_url}
            return heals, quarantines + 1
        incident["action_reason"] = "flaky but not eligible for quarantine"
        return heals, quarantines

    reasons = {
        "APP_BUG": "app bug — needs a human owner",
        "ENVIRONMENT": "environment issue — check infra",
        "UNKNOWN": "unclassified",
        "TEST_BUG": "heal budget reached" if heals >= MAX_HEALS else "no repo_url configured",
        "FLAKY_TIMING": "quarantine budget reached" if quarantines >= MAX_QUARANTINES
        else "no repo_url configured",
    }
    incident["action_reason"] = reasons.get(classification, "report only")
    return heals, quarantines
