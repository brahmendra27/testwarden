"""JUnit XML ingestion — parser units + the one-shot endpoint."""
import io

from flakelens.services.junit import parse_junit

SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="LoginTests" tests="4" failures="1" errors="1" skipped="1">
    <testcase classname="com.acme.LoginTests" name="testValidLogin" time="1.5"/>
    <testcase classname="com.acme.LoginTests" name="testBadPassword" time="0.8">
      <failure type="AssertionError" message="expected error banner">at LoginTests.java:42</failure>
    </testcase>
    <testcase classname="com.acme.LoginTests" name="testTimeout" time="5.0">
      <error type="TimeoutError" message="element not found">stacktrace here</error>
    </testcase>
    <testcase classname="com.acme.LoginTests" name="testMfa" time="0">
      <skipped/>
    </testcase>
  </testsuite>
</testsuites>"""


def test_parse_junit_maps_statuses():
    envelopes = parse_junit(SAMPLE, framework="junit-selenium")
    assert len(envelopes) == 4
    by_title = {e["title"]: e for e in envelopes}

    assert by_title["testValidLogin"]["status"] == "passed"
    assert by_title["testValidLogin"]["duration_ms"] == 1500
    assert by_title["testValidLogin"]["normalized_id"] == "com.acme.LoginTests#testValidLogin"

    fail = by_title["testBadPassword"]
    assert fail["status"] == "failed"
    assert fail["attempts"][0]["error_type"] == "AssertionError"
    assert "expected error banner" in fail["attempts"][0]["error_message"]

    assert by_title["testTimeout"]["status"] == "error"
    assert by_title["testMfa"]["status"] == "skipped"
    assert by_title["testValidLogin"]["framework"] == "junit-selenium"


def test_parse_single_testsuite_root():
    xml = '<testsuite name="S"><testcase classname="S" name="t" time="0.1"/></testsuite>'
    envelopes = parse_junit(xml)
    assert len(envelopes) == 1 and envelopes[0]["status"] == "passed"


def test_junit_endpoint_ingests_and_finalizes(client, project_key):
    _, key = project_key
    response = client.post(
        "/api/v1/ingest/junit",
        data={"framework": "junit-selenium", "branch": "main"},
        files={"file": ("results.xml", io.BytesIO(SAMPLE.encode()), "application/xml")},
        headers={"X-Api-Key": key},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "completed"
    assert body["total"] == 4
    assert body["passed"] == 1
    assert body["failed"] == 1
    assert body["skipped"] == 1

    # Results are queryable like any other run.
    results = client.get(f"/api/v1/runs/{body['run_id']}/results").json()
    assert len(results) == 4
    failed = client.get(f"/api/v1/runs/{body['run_id']}/results?status=failed").json()
    assert failed[0]["error_type"] == "AssertionError"


def test_junit_endpoint_rejects_garbage(client, project_key):
    _, key = project_key
    bad = client.post(
        "/api/v1/ingest/junit",
        files={"file": ("x.xml", io.BytesIO(b"not xml <<<"), "application/xml")},
        headers={"X-Api-Key": key},
    )
    assert bad.status_code == 400
    empty = client.post(
        "/api/v1/ingest/junit",
        files={"file": ("x.xml", io.BytesIO(b"<testsuites></testsuites>"), "application/xml")},
        headers={"X-Api-Key": key},
    )
    assert empty.status_code == 400
