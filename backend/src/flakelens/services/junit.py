"""JUnit XML adapter — the universal ingestion path.

Almost every test framework (Selenium/Java, Jest, Cypress, Playwright-JS, Go,
.NET, Ruby...) emits JUnit XML. Parsing it into FlakeLens' result envelope makes
the platform framework-agnostic in practice, not just in schema.

Structure handled: <testsuites> or a single <testsuite>, each <testcase> with an
optional <failure>/<error>/<skipped> child. classname+name form the stable id.
"""
import xml.etree.ElementTree as ET
from uuid import uuid4


def _clean(text: str | None) -> str | None:
    return text.strip() if text else None


def _case_status(case: ET.Element) -> tuple[str, ET.Element | None]:
    failure = case.find("failure")
    if failure is not None:
        return "failed", failure
    error = case.find("error")
    if error is not None:
        return "error", error
    if case.find("skipped") is not None:
        return "skipped", None
    return "passed", None


def parse_junit(xml_text: str, framework: str = "junit") -> list[dict]:
    """Return a list of result envelopes (dicts) from JUnit XML."""
    root = ET.fromstring(xml_text)
    suites = [root] if root.tag == "testsuite" else root.findall(".//testsuite")
    envelopes: list[dict] = []
    for suite in suites:
        suite_name = suite.get("name") or ""
        for case in suite.findall("testcase"):
            name = case.get("name") or "unknown"
            classname = case.get("classname") or suite_name
            file_path = (case.get("file") or classname.replace(".", "/") or "unknown").replace("\\", "/")
            # Stable identity: classname#name (JUnit's natural key).
            normalized_id = f"{classname}#{name}" if classname else name
            try:
                duration_ms = int(float(case.get("time", "0")) * 1000)
            except (TypeError, ValueError):
                duration_ms = 0

            status, detail = _case_status(case)
            attempt = {"index": 0, "status": status, "duration_ms": duration_ms}
            if detail is not None:
                attempt["error_type"] = detail.get("type") or (
                    "AssertionError" if status == "failed" else "Error"
                )
                attempt["error_message"] = _clean(detail.get("message"))
                attempt["stack_trace"] = _clean(detail.text)
            sysout = case.find("system-out")
            if sysout is not None and sysout.text:
                attempt["stdout"] = sysout.text[:64_000]

            envelopes.append({
                "result_ref": str(uuid4()),
                "framework": framework,
                "normalized_id": normalized_id,
                "file_path": file_path,
                "suite": suite_name or None,
                "title": name,
                "status": status,
                "duration_ms": duration_ms,
                "attempts": [attempt],
                "extras": {"classname": classname} if classname else {},
            })
    return envelopes
