"""AI failure analysis: sends the failure context to the LLM, stores the verdict.

First slice of the phase-2 auto-fix agent — analysis only, no patching yet.
Needs ANTHROPIC_API_KEY or FLAKELENS_LLM_BASE_URL; degrades gracefully without.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from flakelens.config import settings as _settings
from flakelens.models import FailureAnalysis, Run, TestAttempt, TestCase, TestResult
from flakelens.services.llm import make_client, model_kwargs
from flakelens.services.redact import scrub

MODEL = _settings.llm_model

SYSTEM_PROMPT = """You are a senior test automation engineer analyzing a failed UI/API test.
Given the test identity, error, stack trace and retry history, produce a concise analysis:

## Root cause
One short paragraph: what actually went wrong (app bug vs test bug vs environment vs timing).

## Classification
One of: APP_BUG | TEST_BUG | FLAKY_TIMING | ENVIRONMENT | UNKNOWN — with a one-line justification.

## Suggested fix
The most likely fix, as a short concrete code suggestion or checklist (max 5 items).
If the locator/assertion should change, show the exact before/after line.

Be direct and specific. Do not restate the stack trace back; interpret it."""


def _build_context(db: Session, result: TestResult) -> str:
    case = db.get(TestCase, result.test_case_id)
    run = db.get(Run, result.run_id)
    attempts = db.scalars(
        select(TestAttempt)
        .where(TestAttempt.result_id == result.id)
        .order_by(TestAttempt.attempt_index)
    ).all()

    history = db.execute(
        select(TestResult.status, TestResult.is_flaky_in_run)
        .where(TestResult.test_case_id == case.id, TestResult.id < result.id)
        .order_by(TestResult.id.desc())
        .limit(10)
    ).all()
    history_line = ", ".join(
        f"{status}{' (flaky)' if flaky else ''}" for status, flaky in reversed(history)
    ) or "no prior history"

    parts = [
        f"Test: {case.node_id}",
        f"File: {case.file_path}",
        f"Framework: {case.framework}",
        f"Run: #{run.id} branch={run.branch or '?'} commit={run.commit_sha or '?'}",
        f"Final status: {result.status} after {result.attempt_count} attempt(s)",
        f"Recent history (older→newer): {history_line}",
        f"Cross-run flake score: {case.flake_score}",
        "",
    ]
    for attempt in attempts:
        parts.append(f"--- Attempt {attempt.attempt_index + 1}: {attempt.status} "
                     f"({attempt.duration_ms}ms) ---")
        if attempt.error_type or attempt.error_message:
            parts.append(f"Error: {attempt.error_type}: {attempt.error_message}")
        if attempt.stack_trace:
            parts.append(f"Stack trace:\n{attempt.stack_trace[:6000]}")
        if attempt.stdout:
            parts.append(f"Stdout (tail):\n{attempt.stdout[-2000:]}")
    # Sanitize before anything leaves for the LLM: tokens/passwords/cookies can
    # leak into stack traces and logged output.
    return scrub("\n".join(parts))


def analyze_result(db: Session, result: TestResult, force: bool = False) -> FailureAnalysis:
    """Return cached analysis or generate a fresh one via the Claude API."""
    if not force:
        existing = db.scalar(
            select(FailureAnalysis)
            .where(FailureAnalysis.result_id == result.id)
            .order_by(FailureAnalysis.id.desc())
        )
        if existing is not None:
            return existing

    client = make_client()
    response = client.messages.create(
        **model_kwargs(max_tokens=2000),
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_context(db, result)}],
    )
    content = "\n".join(block.text for block in response.content if block.type == "text")

    analysis = FailureAnalysis(result_id=result.id, model=MODEL, content=content)
    db.add(analysis)
    db.commit()
    return analysis
