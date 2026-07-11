"""Reproducer orchestration + job executor.

`search_reproducer` drives the ladder using an injected `run_fn(recipe) -> bool`
(True = the test FAILED under that recipe). It is browser-free and unit-tested
with synthetic flakes. `execute_repro_job` wires `run_fn` to a real cloned repo.
"""
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from flakelens.config import settings
from flakelens.db import SessionLocal
from flakelens.models import Project, ReproJob, Run, TestCase, TestResult
from flakelens.services.reproducer import (
    CATEGORY_CANDIDATES,
    STRESS_ALL,
    is_repro,
    label_recipe,
    merge_recipes,
    minimize_candidates,
)
from flakelens.services.workspace import FixWorkspace, WorkspaceError

BASELINE_RUNS = 6
PROBE_RUNS = 5


def _rate(run_fn, recipe: dict, runs: int) -> float:
    fails = sum(1 for _ in range(runs) if run_fn(recipe))
    return fails / runs


def search_reproducer(run_fn, log, baseline_runs=BASELINE_RUNS, probe_runs=PROBE_RUNS) -> dict:
    """Return {outcome, recipe, recipe_label, fail_rate, baseline_fail_rate, probes}."""
    probes: list[dict] = []

    baseline = _rate(run_fn, {}, baseline_runs)
    log(f"Baseline (no perturbation): {baseline:.0%} fail over {baseline_runs} runs")
    probes.append({"label": "baseline", "recipe": {}, "fail_rate": baseline})

    if baseline >= 0.9:
        # Already fails almost always without help — it's just broken, not flaky.
        return _result("not_reproduced", None, baseline, baseline, probes,
                       note="fails deterministically without perturbation")

    # 1. Stress-all: does ANY chaos surface it?
    stress_rate = _rate(run_fn, STRESS_ALL, probe_runs)
    log(f"Stress-all: {stress_rate:.0%} fail")
    probes.append({"label": "stress-all", "recipe": STRESS_ALL, "fail_rate": stress_rate})
    if not is_repro(stress_rate, baseline):
        return _result("not_reproduced", None, stress_rate, baseline, probes,
                       note="no perturbation combination reproduced the failure")

    # 2. Category bisect: which single categories, alone, reproduce it?
    winners: list[tuple[str, dict]] = []
    for category, fragment, clabel in CATEGORY_CANDIDATES:
        rate = _rate(run_fn, fragment, probe_runs)
        log(f"  {clabel}: {rate:.0%} fail")
        probes.append({"label": clabel, "recipe": fragment, "fail_rate": rate})
        if is_repro(rate, baseline):
            winners.append((category, fragment))

    if not winners:
        # Interaction effect: needs multiple categories together. Report stress-all.
        return _result("reproduced", STRESS_ALL, stress_rate, baseline, probes,
                       note="reproduces only under combined perturbations")

    # 3. Minimize each winning category to its gentlest still-failing condition.
    best_recipe: dict | None = None
    best_rate = 0.0
    for category, _fragment in winners:
        chosen: dict | None = None
        chosen_rate = 0.0
        for candidate, mlabel in minimize_candidates(category):
            rate = _rate(run_fn, candidate, probe_runs)
            log(f"  minimize {mlabel}: {rate:.0%} fail")
            probes.append({"label": f"minimize {mlabel}", "recipe": candidate, "fail_rate": rate})
            if is_repro(rate, baseline):
                chosen, chosen_rate = candidate, rate  # keep the gentlest that still fails
        if chosen is not None and chosen_rate >= best_rate:
            best_recipe, best_rate = chosen, chosen_rate

    if best_recipe is None:
        best_recipe = merge_recipes([f for _, f in winners])
        best_rate = stress_rate
    return _result("reproduced", best_recipe, best_rate, baseline, probes)


def _result(outcome, recipe, fail_rate, baseline, probes, note=None) -> dict:
    return {
        "outcome": outcome,
        "recipe": recipe,
        "recipe_label": label_recipe(recipe) if recipe else (note or "not reproduced"),
        "fail_rate": round(fail_rate, 3),
        "baseline_fail_rate": round(baseline, 3),
        "probes": probes,
        "note": note,
    }


def _pytest_arg(node_id: str) -> str:
    """FlakeLens node_id -> a pytest selector, dropping the [browser] param suffix
    so the test collects under whatever browser the runner defaults to."""
    return node_id.split("[", 1)[0]


def execute_repro_job(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.get(ReproJob, job_id)

        def log(line: str) -> None:
            job.log = (job.log or "") + line + "\n"
            db.commit()

        try:
            case = db.get(TestCase, job.test_case_id)
            project = db.get(Project, case.project_id)
            job.status = "running"
            db.commit()

            if not project.repo_url:
                raise WorkspaceError("Project has no repo_url configured")

            last_run = db.scalar(
                select(Run).join(TestResult, TestResult.run_id == Run.id)
                .where(TestResult.test_case_id == case.id)
                .order_by(Run.id.desc()).limit(1)
            )
            workdir = Path(settings.artifact_dir).parent / "agent-workspaces" / f"repro-{job.id}"
            if workdir.exists():
                shutil.rmtree(workdir, ignore_errors=True)
            workspace = FixWorkspace(project.repo_url, workdir)
            log(f"Cloning {project.repo_url} ...")
            workspace.clone(commit_sha=last_run.commit_sha if last_run else None)

            # Locate the test's subproject dir (the dir containing its file).
            candidates = workspace.list_files(Path(case.file_path).name)
            cwd = "."
            selector = _pytest_arg(case.node_id)
            if candidates:
                rel = candidates[0]
                depth = case.file_path.replace("\\", "/").count("/") + 1
                parts = rel.split("/")
                cwd = "/".join(parts[:-min(depth, len(parts))]) or "."
                selector = "/".join(parts[-min(depth, len(parts)):])
            selector = _pytest_arg(selector)
            log(f"Test selector: {selector} (cwd={cwd})")

            def run_fn(recipe: dict) -> bool:
                env = {"FLAKELENS_ENABLED": "false"}
                if recipe:
                    env["FLAKELENS_PERTURB"] = json.dumps(recipe)
                output = workspace.run_tests(f"{selector} -p no:flakelens", cwd=cwd, extra_env=env)
                return "exit code: 0" not in output.splitlines()[0] if output else True

            log(f"Starting reproducer search for {case.node_id} ...")
            started = time.monotonic()
            result = search_reproducer(run_fn, log)
            log(f"Search finished in {time.monotonic() - started:.0f}s: {result['outcome']}")

            job.outcome = result["outcome"]
            job.recipe = result["recipe"]
            job.recipe_label = result["recipe_label"]
            job.fail_rate = result["fail_rate"]
            job.baseline_fail_rate = result["baseline_fail_rate"]
            job.probes = result["probes"]
            job.status = "completed"
        except Exception as exc:
            job.status = "failed"
            job.outcome = "error"
            job.error = str(exc)[:2000]
            log(f"ERROR: {exc}")
        finally:
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()
