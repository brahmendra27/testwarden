"""GitHub Checks — post a flakiness-adjusted verdict onto a commit/PR.

The key value: a raw pass/fail check is noisy because flaky failures block merges
that shouldn't. This verdict treats known-flaky failures as non-blocking (neutral)
and only fails the check on genuinely new/non-flaky failures — with the offending
tests listed so a reviewer knows exactly what to look at.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from flakelens.models import Run, TestCase, TestResult
from flakelens.services.workspace import GITHUB_RE


def compute_verdict(db: Session, run: Run) -> dict:
    """Classify a run's failures into blocking (real) vs non-blocking (flaky)."""
    rows = db.execute(
        select(TestResult, TestCase)
        .join(TestCase, TestCase.id == TestResult.test_case_id)
        .where(TestResult.run_id == run.id, TestResult.status.in_(("failed", "error")))
    ).all()
    blocking, flaky = [], []
    for result, case in rows:
        (flaky if (case.is_flaky or result.is_flaky_in_run) else blocking).append(case.node_id)

    if blocking:
        conclusion = "failure"
        title = f"{len(blocking)} real failure(s)" + (f", {len(flaky)} flaky (ignored)" if flaky else "")
    elif flaky:
        conclusion = "neutral"
        title = f"Only flaky failures ({len(flaky)}) — not blocking"
    else:
        conclusion = "success"
        title = f"All {run.passed}/{run.total} passed"

    lines = [f"**FlakeLens verdict for run #{run.id}**", ""]
    if blocking:
        lines.append("### ❌ Blocking failures (new / not flaky)")
        lines += [f"- `{n}`" for n in blocking[:20]]
    if flaky:
        lines.append("\n### ⚠️ Flaky failures (not blocking merge)")
        lines += [f"- `{n}`" for n in flaky[:20]]
    if not blocking and not flaky:
        lines.append("Everything green. ✅")

    return {"conclusion": conclusion, "title": title, "summary": "\n".join(lines),
            "blocking": blocking, "flaky": flaky}


def post_check(repo_url: str, commit_sha: str, verdict: dict, token: str) -> str:
    import httpx

    match = GITHUB_RE.search(repo_url or "")
    if match is None:
        raise ValueError("repo_url is not a GitHub URL")
    owner, name = match.group(1), match.group(2)
    response = httpx.post(
        f"https://api.github.com/repos/{owner}/{name}/check-runs",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={
            "name": "FlakeLens",
            "head_sha": commit_sha,
            "status": "completed",
            "conclusion": verdict["conclusion"],
            "output": {"title": verdict["title"], "summary": verdict["summary"]},
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json().get("html_url", "")
