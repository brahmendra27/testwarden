import hashlib
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from flakelens.models import Run, TestAttempt, TestCase, TestResult
from flakelens.schemas.ingest import ResultEnvelope, RunCreate

STDIO_CAP = 64 * 1024
_FAILING = ("failed", "error")


def compute_case_key(project_id: int, framework: str, normalized_id: str) -> str:
    family = framework.split("-", 1)[0]
    normalized = normalized_id.replace("\\", "/")
    return hashlib.sha256(f"{project_id}\n{family}\n{normalized}".encode()).hexdigest()


def compute_failure_fingerprint(
    error_type: str | None, error_message: str | None, file_path: str
) -> str | None:
    if not error_type and not error_message:
        return None
    first_line = (error_message or "").strip().splitlines()[0] if error_message else ""
    raw = f"{error_type or ''}\n{first_line[:200]}\n{file_path}"
    return hashlib.sha256(raw.encode()).hexdigest()


def get_or_create_run(db: Session, project_id: int, payload: RunCreate) -> tuple[Run, bool]:
    existing = db.scalar(select(Run).where(Run.run_uuid == payload.run_uuid))
    if existing is not None:
        return existing, False
    run = Run(
        project_id=project_id,
        run_uuid=payload.run_uuid,
        framework=payload.framework,
        started_at=payload.started_at or datetime.now(timezone.utc),
        branch=payload.branch,
        commit_sha=payload.commit_sha,
        ci_url=payload.ci_url,
        environment=payload.environment,
        labels=payload.labels or {},
    )
    db.add(run)
    db.flush()
    return run, True


def _upsert_test_case(db: Session, project_id: int, run: Run, envelope: ResultEnvelope) -> TestCase:
    case_key = compute_case_key(project_id, envelope.framework, envelope.normalized_id)
    case = db.scalar(
        select(TestCase).where(TestCase.project_id == project_id, TestCase.case_key == case_key)
    )
    if case is None:
        case = TestCase(
            project_id=project_id,
            case_key=case_key,
            node_id=envelope.normalized_id,
            file_path=envelope.file_path.replace("\\", "/"),
            suite=envelope.suite,
            title=envelope.title,
            framework=envelope.framework,
            first_seen_run_id=run.id,
            last_seen_run_id=run.id,
        )
        db.add(case)
        db.flush()
    else:
        case.node_id = envelope.normalized_id
        case.file_path = envelope.file_path.replace("\\", "/")
        case.suite = envelope.suite
        case.title = envelope.title
        case.last_seen_run_id = run.id
    return case


def ingest_results(
    db: Session, project_id: int, run: Run, envelopes: list[ResultEnvelope]
) -> dict[str, int]:
    """Store a batch of result envelopes; returns result_ref -> result_id."""
    ref_map: dict[str, int] = {}
    for envelope in envelopes:
        case = _upsert_test_case(db, project_id, run, envelope)

        existing = db.scalar(
            select(TestResult).where(
                TestResult.run_id == run.id, TestResult.test_case_id == case.id
            )
        )
        if existing is not None:
            # Idempotency: a re-sent envelope maps to the already-stored result.
            ref_map[envelope.result_ref] = existing.id
            continue

        attempts = envelope.attempts or []
        final_status = envelope.status
        is_flaky_in_run = final_status == "passed" and any(
            a.status in _FAILING for a in attempts
        )
        failing = [a for a in attempts if a.status in _FAILING]
        last_failing = failing[-1] if failing else None

        result = TestResult(
            run_id=run.id,
            test_case_id=case.id,
            status=final_status,
            is_flaky_in_run=is_flaky_in_run,
            attempt_count=max(1, len(attempts)),
            duration_ms=envelope.duration_ms,
            error_type=last_failing.error_type if last_failing else None,
            error_message=(last_failing.error_message or "")[:10_000] if last_failing else None,
            failure_fingerprint=(
                compute_failure_fingerprint(
                    last_failing.error_type, last_failing.error_message, envelope.file_path
                )
                if last_failing and final_status in _FAILING
                else None
            ),
            extras=envelope.extras or {},
        )
        db.add(result)
        db.flush()
        ref_map[envelope.result_ref] = result.id

        if not attempts:
            db.add(
                TestAttempt(
                    result_id=result.id,
                    attempt_index=0,
                    status=final_status,
                    duration_ms=envelope.duration_ms,
                )
            )
        for attempt in attempts:
            db.add(
                TestAttempt(
                    result_id=result.id,
                    attempt_index=attempt.index,
                    status=attempt.status,
                    duration_ms=attempt.duration_ms,
                    error_type=attempt.error_type,
                    error_message=(attempt.error_message or None),
                    stack_trace=(attempt.stack_trace or "")[:200_000] or None,
                    stdout=(attempt.stdout or "")[:STDIO_CAP] or None,
                    stderr=(attempt.stderr or "")[:STDIO_CAP] or None,
                )
            )
    db.flush()
    return ref_map
