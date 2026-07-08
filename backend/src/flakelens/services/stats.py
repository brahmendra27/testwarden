"""Flaky detection and rolling per-test stats.

The scoring core is pure functions over status-token sequences so it can be
unit-tested with synthetic histories and recomputed from raw results at any time.

Window entries are small dicts: {"t": token, "d": duration_ms, "r": run_id}
Tokens: "P" passed, "A" passed-but-flaky-in-run, "F" failed, "E" error.
Skipped / xfailed / xpassed results are excluded from the window.
"""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from flakelens.models import Run, TestCase, TestResult

STATS_WINDOW = 20
FLAKE_THRESHOLD = 0.3
MIN_HISTORY = 5
CLEAN_STREAK = 10

_PASS_TOKENS = {"P", "A"}
_FAIL_TOKENS = {"F", "E"}


def window_token(status: str, is_flaky_in_run: bool) -> str | None:
    """Map a final result to its window token; None means excluded."""
    if status == "passed":
        return "A" if is_flaky_in_run else "P"
    if status == "failed":
        return "F"
    if status == "error":
        return "E"
    return None


def result_token(result) -> str | None:
    """Window token for a stored TestResult, honoring quarantine.

    Quarantined tests run under xfail so CI stays green, but their real
    outcome (xpassed = healthy, xfailed = still broken) must keep feeding the
    flake window — that signal is what eventually releases them.
    """
    if (result.extras or {}).get("quarantined"):
        if result.status == "xpassed":
            return "P"
        if result.status == "xfailed":
            return "F"
    return window_token(result.status, result.is_flaky_in_run)


def compute_case_stats(entries: list[dict]) -> dict:
    tokens = [e["t"] for e in entries]
    n = len(tokens)
    flips = 0
    for prev, cur in zip(tokens, tokens[1:]):
        if (prev in _PASS_TOKENS) != (cur in _PASS_TOKENS):
            flips += 1
    flip_rate = flips / (n - 1) if n > 1 else 0.0
    intra_rate = tokens.count("A") / n if n else 0.0
    flake_score = 1.0 - (1.0 - flip_rate) * (1.0 - intra_rate)

    is_flaky = flake_score >= FLAKE_THRESHOLD and n >= MIN_HISTORY
    # Aging out: a long clean streak heals the flag regardless of older history.
    if n >= CLEAN_STREAK and all(t == "P" for t in tokens[-CLEAN_STREAK:]):
        is_flaky = False

    durations = sorted(e.get("d", 0) for e in entries)
    avg = int(sum(durations) / n) if n else 0
    p95 = durations[min(n - 1, int(0.95 * n))] if n else 0

    return {
        "flip_count": flips,
        "flake_score": round(flake_score, 4),
        "is_flaky": is_flaky,
        "avg_duration_ms": avg,
        "p95_duration_ms": p95,
    }


def apply_result_to_case(case: TestCase, result: TestResult, run_id: int) -> None:
    """Append one final result to the case's rolling window and refresh stats."""
    case.last_status = result.status
    token = result_token(result)
    if token is None:
        return
    entries = list(case.recent_statuses or [])
    entries.append({"t": token, "d": result.duration_ms, "r": run_id})
    entries = entries[-STATS_WINDOW:]
    case.recent_statuses = entries
    stats = compute_case_stats(entries)
    case.flip_count = stats["flip_count"]
    case.flake_score = stats["flake_score"]
    case.is_flaky = stats["is_flaky"]
    case.avg_duration_ms = stats["avg_duration_ms"]
    case.p95_duration_ms = stats["p95_duration_ms"]
    case.stats_updated_at = datetime.now(timezone.utc)


def finalize_run(db: Session, run: Run, finished_at: datetime | None = None) -> None:
    """Write denormalized run counts and roll every touched test case's stats forward."""
    results = db.scalars(select(TestResult).where(TestResult.run_id == run.id)).all()
    run.total = len(results)
    run.passed = sum(1 for r in results if r.status == "passed")
    run.failed = sum(1 for r in results if r.status == "failed")
    run.skipped = sum(1 for r in results if r.status in ("skipped", "xfailed"))
    run.error_count = sum(1 for r in results if r.status == "error")
    run.flaky_count = sum(1 for r in results if r.is_flaky_in_run)
    run.finished_at = finished_at or datetime.now(timezone.utc)
    run.status = "completed"
    started = run.started_at
    if started is not None and started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    finished = run.finished_at
    if finished.tzinfo is None:
        finished = finished.replace(tzinfo=timezone.utc)
    run.duration_ms = max(0, int((finished - started).total_seconds() * 1000))

    for result in results:
        case = db.get(TestCase, result.test_case_id)
        case.last_seen_run_id = run.id
        apply_result_to_case(case, result, run.id)


def recompute_project_stats(db: Session, project_id: int) -> int:
    """Rebuild every test case's rolling window from raw results (safety net)."""
    case_ids = db.scalars(select(TestCase.id).where(TestCase.project_id == project_id)).all()
    for case_id in case_ids:
        case = db.get(TestCase, case_id)
        rows = db.execute(
            select(TestResult, Run.id)
            .join(Run, Run.id == TestResult.run_id)
            .where(TestResult.test_case_id == case_id, Run.status == "completed")
            .order_by(Run.started_at, TestResult.id)
        ).all()
        entries = []
        last_status = None
        for result, run_id in rows:
            last_status = result.status
            token = result_token(result)
            if token is not None:
                entries.append({"t": token, "d": result.duration_ms, "r": run_id})
        entries = entries[-STATS_WINDOW:]
        case.recent_statuses = entries
        case.last_status = last_status
        stats = compute_case_stats(entries)
        case.flip_count = stats["flip_count"]
        case.flake_score = stats["flake_score"]
        case.is_flaky = stats["is_flaky"]
        case.avg_duration_ms = stats["avg_duration_ms"]
        case.p95_duration_ms = stats["p95_duration_ms"]
        case.stats_updated_at = datetime.now(timezone.utc)
    db.commit()
    return len(case_ids)


def sweep_interrupted_runs(db: Session, ttl_minutes: int) -> int:
    """Mark runs stuck in 'running' longer than the TTL as interrupted."""
    cutoff = datetime.now(timezone.utc).timestamp() - ttl_minutes * 60
    stale = db.scalars(select(Run).where(Run.status == "running")).all()
    count = 0
    for run in stale:
        started = run.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        if started.timestamp() < cutoff:
            run.status = "interrupted"
            count += 1
    db.commit()
    return count
