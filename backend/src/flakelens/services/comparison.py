from sqlalchemy import select
from sqlalchemy.orm import Session

from flakelens.models import TestCase, TestResult

_FAILING = ("failed", "error")


def _results_by_case(db: Session, run_id: int) -> dict[int, TestResult]:
    rows = db.scalars(select(TestResult).where(TestResult.run_id == run_id)).all()
    return {r.test_case_id: r for r in rows}


def classify(base: TestResult | None, head: TestResult | None) -> str | None:
    if base is None and head is not None:
        return "new"
    if base is not None and head is None:
        return "removed"
    b, h = base.status, head.status
    if h in _FAILING and b == "passed":
        return "newly_failing"
    if h == "passed" and b in _FAILING and not head.is_flaky_in_run:
        return "fixed"
    if head.is_flaky_in_run and not base.is_flaky_in_run:
        return "newly_flaky"
    if h in _FAILING and b in _FAILING:
        return "still_failing"
    return None  # unchanged / uninteresting


def compare_runs(db: Session, base_run_id: int, head_run_id: int) -> dict:
    base_results = _results_by_case(db, base_run_id)
    head_results = _results_by_case(db, head_run_id)
    case_ids = set(base_results) | set(head_results)
    cases = {
        c.id: c
        for c in db.scalars(select(TestCase).where(TestCase.id.in_(case_ids))).all()
    }

    buckets: dict[str, list[dict]] = {
        "newly_failing": [],
        "fixed": [],
        "newly_flaky": [],
        "still_failing": [],
        "new": [],
        "removed": [],
    }
    for case_id in case_ids:
        base = base_results.get(case_id)
        head = head_results.get(case_id)
        bucket = classify(base, head)
        if bucket is None:
            continue
        case = cases[case_id]
        buckets[bucket].append(
            {
                "test_case_id": case_id,
                "node_id": case.node_id,
                "file_path": case.file_path,
                "title": case.title,
                "base_status": base.status if base else None,
                "head_status": head.status if head else None,
                "head_flaky_in_run": head.is_flaky_in_run if head else False,
                "error_message": (head.error_message if head else None)
                or (base.error_message if base else None),
            }
        )
    for bucket in buckets.values():
        bucket.sort(key=lambda item: item["node_id"])
    return {
        "counts": {name: len(items) for name, items in buckets.items()},
        "buckets": buckets,
    }
