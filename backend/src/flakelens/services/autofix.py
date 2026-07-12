"""The auto-fix agent: Claude patches a failing test in an isolated clone,
verifies by re-running it, then commits to a branch and (if possible) opens a PR.
"""
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from flakelens.config import settings
from flakelens.db import SessionLocal
from flakelens.models import (
    AgentJob,
    FailureAnalysis,
    Project,
    Run,
    TestAttempt,
    TestCase,
    TestResult,
)
from flakelens.services.llm import make_client, model_kwargs
from flakelens.services.workspace import FixWorkspace, WorkspaceError

from flakelens.config import settings as _settings

MODEL = _settings.llm_model
MAX_ITERATIONS = 25

SYSTEM_PROMPT = """You are FlakeLens's autonomous fix agent. A test in this repository failed \
and your job is to fix it with the smallest correct change.

Rules:
- First reproduce your understanding: read the failing test and the code it touches.
- Decide whether this is a TEST bug (bad locator/assertion/timing) or an APP bug \
(the code under test is wrong). Fix the actual root cause.
- Make the minimal change. Never refactor, rename, or touch unrelated code.
- The recorded file path may be relative to a subproject; use list_files to locate files.
- Verify: run the failing test with run_tests until it passes. If it needs a browser or \
services that are unavailable here, say so in your summary instead of guessing.
- When the test passes (or you conclude it cannot be fixed here), call finish with a short \
summary: root cause, what you changed, and how you verified it.
- If you cannot fix it, call finish with outcome "cannot_fix" and explain why."""

TOOLS = [
    {
        "name": "list_files",
        "description": "List files in the repository matching a glob pattern, e.g. '*.py' or 'test_demo*'.",
        "input_schema": {
            "type": "object",
            "properties": {"pattern": {"type": "string", "description": "Glob pattern (searched recursively)"}},
            "required": ["pattern"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a file from the repository (path relative to repo root).",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "edit_file",
        "description": "Replace an exact string in a file. old_str must appear exactly once; include surrounding lines for uniqueness.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_str": {"type": "string"},
                "new_str": {"type": "string"},
            },
            "required": ["path", "old_str", "new_str"],
        },
    },
    {
        "name": "write_file",
        "description": "Create or overwrite a file with the given content.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    },
    {
        "name": "run_tests",
        "description": "Run pytest with the given arguments (e.g. 'tests/test_login.py::test_valid -x'). cwd is a directory relative to repo root, for subproject test suites.",
        "input_schema": {
            "type": "object",
            "properties": {
                "args": {"type": "string"},
                "cwd": {"type": "string", "description": "Directory to run in, default repo root"},
            },
            "required": ["args"],
        },
    },
    {
        "name": "finish",
        "description": "End the session once the fix is verified (or you conclude it cannot be fixed).",
        "input_schema": {
            "type": "object",
            "properties": {
                "outcome": {"type": "string", "enum": ["fixed", "cannot_fix"]},
                "summary": {"type": "string", "description": "Root cause, change made, verification"},
            },
            "required": ["outcome", "summary"],
        },
    },
]


def _dispatch(workspace: FixWorkspace, name: str, tool_input: dict) -> str:
    try:
        if name == "list_files":
            files = workspace.list_files(tool_input.get("pattern") or "*")
            return "\n".join(files) or "no matches"
        if name == "read_file":
            return workspace.read_file(tool_input["path"])
        if name == "edit_file":
            return workspace.edit_file(tool_input["path"], tool_input["old_str"], tool_input["new_str"])
        if name == "write_file":
            return workspace.write_file(tool_input["path"], tool_input["content"])
        if name == "run_tests":
            return workspace.run_tests(tool_input["args"], tool_input.get("cwd", "."))
    except KeyError as exc:  # malformed call (weak models) → correctable feedback
        raise WorkspaceError(f"missing required argument {exc} for {name}") from exc
    raise WorkspaceError(f"Unknown tool {name}")


def _preview(tool_input: dict) -> str:
    text = ", ".join(f"{k}={str(v)[:80]!r}" for k, v in tool_input.items() if k != "content")
    return text[:200]


def run_agent(client, workspace: FixWorkspace, task: str, log, system: str = SYSTEM_PROMPT) -> dict:
    """Manual tool loop. Returns {'outcome': 'fixed'|'cannot_fix'|'gave_up', 'summary': str}.

    A finish(fixed) is only accepted after the agent has actually changed a file
    AND run the tests afterwards — weaker (especially local) models sometimes
    hallucinate completion on turn one; rejecting the premature finish pushes
    them to do the work instead of ending the job.
    """
    messages = [{"role": "user", "content": task}]
    changed = False        # any edit/write since start
    verified = False       # run_tests called after the last change
    nudges = 0             # text-only replies answered with a protocol reminder
    for iteration in range(1, MAX_ITERATIONS + 1):
        response = client.messages.create(
            **model_kwargs(max_tokens=6000),
            system=system,
            tools=TOOLS,
            messages=messages,
        )
        tool_uses = [block for block in response.content if block.type == "tool_use"]
        if not tool_uses:
            text = "\n".join(b.text for b in response.content if b.type == "text")
            # Weaker models sometimes narrate ("I will now run the tests")
            # instead of calling the tool — remind them of the protocol twice
            # before giving up.
            if nudges < 2:
                nudges += 1
                log(f"[{iteration}] (text-only reply — nudging to use tools, {nudges}/2)")
                messages.append({"role": "assistant",
                                 "content": response.content
                                 or [{"type": "text", "text": "(empty reply)"}]})
                messages.append({"role": "user", "content":
                                 "Do not reply with prose. Respond with a tool call: continue the "
                                 "work (edit_file/write_file/run_tests) or call finish."})
                continue
            return {"outcome": "gave_up", "summary": text or "Agent stopped without calling finish."}

        messages.append({"role": "assistant", "content": response.content})
        results = []
        for tool in tool_uses:
            if tool.name == "finish":
                outcome = tool.input.get("outcome", "fixed")
                if outcome == "fixed" and not (changed and verified):
                    reason = ("you have not modified any file yet" if not changed
                              else "you have not run the tests since your last change")
                    log(f"[{iteration}] finish(fixed) REJECTED: {reason}")
                    results.append({
                        "type": "tool_result", "tool_use_id": tool.id,
                        "content": f"Rejected: {reason}. Actually make the fix, verify it "
                                   "with run_tests, and only then call finish.",
                        "is_error": True,
                    })
                    continue
                log(f"[{iteration}] finish({outcome})")
                return {"outcome": outcome, "summary": tool.input.get("summary", "")}
            log(f"[{iteration}] {tool.name}({_preview(tool.input)})")
            try:
                output = _dispatch(workspace, tool.name, tool.input)
                results.append({"type": "tool_result", "tool_use_id": tool.id, "content": output})
                if tool.name in ("edit_file", "write_file"):
                    changed, verified = True, False
                elif tool.name == "run_tests":
                    verified = True
            except WorkspaceError as exc:
                results.append({
                    "type": "tool_result", "tool_use_id": tool.id,
                    "content": f"Error: {exc}", "is_error": True,
                })
        messages.append({"role": "user", "content": results})
    return {"outcome": "gave_up", "summary": f"Stopped after {MAX_ITERATIONS} iterations."}


def latest_reproducer_recipe(db, case_id: int):
    """The stored minimal recipe that reproduces this test's flake, if any."""
    from flakelens.models import ReproJob

    job = db.scalar(
        select(ReproJob)
        .where(ReproJob.test_case_id == case_id, ReproJob.outcome == "reproduced")
        .order_by(ReproJob.id.desc())
    )
    return (job.recipe, job.recipe_label) if job and job.recipe else (None, None)


def _build_task(db, result: TestResult, case: TestCase, run: Run) -> str:
    attempts = db.scalars(
        select(TestAttempt).where(TestAttempt.result_id == result.id)
        .order_by(TestAttempt.attempt_index)
    ).all()
    failing = [a for a in attempts if a.status in ("failed", "error")]
    last = failing[-1] if failing else None
    analysis = db.scalar(
        select(FailureAnalysis).where(FailureAnalysis.result_id == result.id)
        .order_by(FailureAnalysis.id.desc())
    )
    parts = [
        f"Failing test: {case.node_id}",
        f"Recorded file path (may be relative to a subproject): {case.file_path}",
        f"Status: {result.status} after {result.attempt_count} attempt(s); "
        f"cross-run flake score {case.flake_score}",
    ]
    if last is not None:
        parts.append(f"Error: {last.error_type}: {last.error_message}")
        if last.stack_trace:
            parts.append(f"Stack trace:\n{last.stack_trace[:6000]}")
    if analysis is not None:
        parts.append(f"\nPrior AI analysis of this failure:\n{analysis.content[:3000]}")
    _recipe, recipe_label = latest_reproducer_recipe(db, case.id)
    if recipe_label:
        parts.append(
            f"\nFlakeLens Reproducer found this failure is DETERMINISTIC under: {recipe_label}.\n"
            "This is a race/timing bug, not a random flake — fix the underlying handling "
            "(add awaits/retries/guards for that condition), not the test's assertions."
        )
    parts.append("\nFind the root cause, apply the minimal fix, verify with run_tests, then call finish.")
    from flakelens.services.redact import scrub

    # Scrub secrets from error/stack/stdout evidence before it reaches the LLM.
    # (File contents the agent reads via tools are intentionally NOT scrubbed —
    # it needs the real source to fix the bug.)
    return scrub("\n".join(parts))


def _slug(text: str, limit: int = 40) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:limit]


def _verify_under_recipe(workspace, case, recipe: dict, log, runs: int = 5) -> bool:
    """Run the (now-patched) test `runs` times under the reproducer recipe.
    The fix holds only if it passes every time under the failure condition."""
    import json

    selector = case.node_id.split("[", 1)[0]
    candidates = workspace.list_files(Path(case.file_path).name)
    cwd = "."
    if candidates:
        rel = candidates[0]
        depth = case.file_path.replace("\\", "/").count("/") + 1
        parts = rel.split("/")
        cwd = "/".join(parts[:-min(depth, len(parts))]) or "."
        selector = "/".join(parts[-min(depth, len(parts)):]).split("[", 1)[0]
    log(f"Verifying fix under reproducer condition ({runs} runs) ...")
    for i in range(runs):
        output = workspace.run_tests(
            f"{selector} -p no:flakelens", cwd=cwd,
            extra_env={"FLAKELENS_ENABLED": "false", "FLAKELENS_PERTURB": json.dumps(recipe)},
        )
        passed = bool(output) and "exit code: 0" in output.splitlines()[0]
        log(f"  run {i + 1}/{runs}: {'pass' if passed else 'FAIL'}")
        if not passed:
            return False
    return True


def execute_autofix_job(job_id: int) -> None:
    """Runs in a background thread with its own session; never raises."""
    db = SessionLocal()
    try:
        job = db.get(AgentJob, job_id)

        def log(line: str) -> None:
            job.log = (job.log or "") + line + "\n"
            db.commit()

        try:
            result = db.get(TestResult, job.result_id)
            case = db.get(TestCase, result.test_case_id)
            run = db.get(Run, result.run_id)
            project = db.get(Project, case.project_id)

            job.status = "running"
            job.model = MODEL
            db.commit()

            if not project.repo_url:
                raise WorkspaceError(
                    "Project has no repo_url configured. Set it via "
                    f"PATCH /api/v1/projects/{project.slug}"
                )

            workdir = Path(settings.artifact_dir).parent / "agent-workspaces" / f"job-{job.id}"
            if workdir.exists():
                shutil.rmtree(workdir, ignore_errors=True)
            workspace = FixWorkspace(project.repo_url, workdir)

            log(f"Cloning {project.repo_url} ...")
            workspace.clone(commit_sha=run.commit_sha)
            base_branch = workspace.default_branch()
            branch = f"selfheal/fix-{_slug(case.title)}-{job.id}"
            workspace.create_branch(branch)
            job.branch = branch
            log(f"Branch {branch} created from {base_branch}. Starting agent ({MODEL}) ...")

            client = make_client()
            started = time.monotonic()
            verdict = run_agent(client, workspace, _build_task(db, result, case, run), log)
            log(f"Agent finished in {time.monotonic() - started:.0f}s: {verdict['outcome']}")

            diff = workspace.diff()
            job.summary = verdict["summary"]
            job.diff = diff or None

            if verdict["outcome"] != "fixed" or not diff.strip():
                job.status = "failed"
                job.error = (
                    "Agent made no changes" if not diff.strip()
                    else f"Agent outcome: {verdict['outcome']}"
                )
            else:
                # If the Reproducer found a deterministic trigger, prove the fix
                # holds UNDER that exact condition — not just a lucky green run.
                recipe, recipe_label = latest_reproducer_recipe(db, case.id)
                if recipe:
                    verified = _verify_under_recipe(workspace, case, recipe, log)
                    verdict_note = (
                        f"\n\nVerified under reproducer ({recipe_label}): "
                        f"{'PASSED 5/5' if verified else 'STILL FAILS — fix incomplete'}."
                    )
                    verdict["summary"] += verdict_note
                    if not verified:
                        job.summary = verdict["summary"]
                        job.status = "failed"
                        job.error = f"Fix did not hold under reproducer condition: {recipe_label}"
                        job.finished_at = datetime.now(timezone.utc)
                        db.commit()
                        return
                workspace.commit(f"fix: {case.title} (FlakeLens SelfHeal #{job.id})")
                log("Changes committed.")
                token = os.environ.get("FLAKELENS_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
                if token and workspace.github_repo():
                    pr_body = (
                        f"Automated fix for `{case.node_id}` "
                        f"(run #{run.id}, result #{result.id}).\n\n{verdict['summary']}\n\n"
                        "🤖 Generated by the FlakeLens SelfHeal agent — review before merging."
                    )
                    job.pr_url = workspace.push_and_open_pr(
                        branch, base_branch, f"[FlakeLens] Fix {case.title}", pr_body, token
                    )
                    log(f"Pull request opened: {job.pr_url}")
                else:
                    log("No GitHub token / remote - fix left on local branch; diff available below.")
                job.status = "completed"
        except Exception as exc:  # any failure lands in the job record, not the server log
            job.status = "failed"
            job.error = str(exc)[:2000]
            log(f"ERROR: {exc}")
        finally:
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()
