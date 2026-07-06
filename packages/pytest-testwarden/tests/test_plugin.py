def _by_title(client):
    return {envelope["title"]: envelope for envelope in client.envelopes}


def test_statuses_and_error_capture(pytester, fake_client):
    pytester.makepyfile(
        test_sample="""
        import pytest

        def test_ok():
            assert True

        def test_broken():
            assert 1 == 2, "numbers diverged"

        @pytest.mark.skip(reason="not today")
        def test_skipped():
            pass

        @pytest.mark.xfail(reason="known bug")
        def test_expected_failure():
            assert False
        """
    )
    result = pytester.runpytest_inprocess()
    result.assert_outcomes(passed=1, failed=1, skipped=1, xfailed=1)

    client = fake_client.instances[0]
    assert client.finished is True
    assert len(client.runs) == 1

    envelopes = _by_title(client)
    assert envelopes["test_ok"]["status"] == "passed"
    assert envelopes["test_skipped"]["status"] == "skipped"
    assert envelopes["test_expected_failure"]["status"] == "xfailed"

    broken = envelopes["test_broken"]
    assert broken["status"] == "failed"
    assert broken["file_path"] == "test_sample.py"
    attempt = broken["attempts"][0]
    assert attempt["error_type"] == "AssertionError"
    assert "numbers diverged" in attempt["error_message"]
    assert "assert 1 == 2" in attempt["stack_trace"]


def test_rerun_produces_multiple_attempts(pytester, fake_client):
    pytester.makepyfile(
        test_flaky="""
        from pathlib import Path

        def test_flaky(tmp_path_factory):
            marker = Path("attempt-marker.txt")
            if not marker.exists():
                marker.write_text("tried once")
                raise TimeoutError("first attempt times out")
        """
    )
    result = pytester.runpytest_inprocess("--reruns", "1")
    outcomes = result.parseoutcomes()
    assert outcomes.get("passed") == 1
    assert outcomes.get("rerun") == 1

    client = fake_client.instances[0]
    assert len(client.envelopes) == 1
    envelope = client.envelopes[0]
    assert envelope["status"] == "passed"
    statuses = [attempt["status"] for attempt in envelope["attempts"]]
    assert statuses == ["failed", "passed"]
    assert envelope["attempts"][0]["error_type"] == "TimeoutError"


def test_setup_failure_reports_error(pytester, fake_client):
    pytester.makepyfile(
        test_err="""
        import pytest

        @pytest.fixture
        def broken_fixture():
            raise RuntimeError("fixture exploded")

        def test_with_broken_fixture(broken_fixture):
            pass
        """
    )
    result = pytester.runpytest_inprocess()
    result.assert_outcomes(errors=1)
    envelope = fake_client.instances[0].envelopes[0]
    assert envelope["status"] == "error"


def test_no_config_means_no_reporting(pytester, fake_client, monkeypatch):
    monkeypatch.delenv("TESTWARDEN_URL")
    monkeypatch.delenv("TESTWARDEN_API_KEY")
    pytester.makepyfile("def test_quiet(): pass")
    result = pytester.runpytest_inprocess()
    result.assert_outcomes(passed=1)
    assert fake_client.instances == []


def test_explicit_disable(pytester, fake_client, monkeypatch):
    monkeypatch.setenv("TESTWARDEN_ENABLED", "false")
    pytester.makepyfile("def test_quiet(): pass")
    result = pytester.runpytest_inprocess()
    result.assert_outcomes(passed=1)
    assert fake_client.instances == []


def test_attach_fixture_uploads_artifact(pytester, fake_client):
    pytester.makepyfile(
        test_attach="""
        from pathlib import Path

        def test_with_attachment(testwarden_attach, tmp_path):
            log = tmp_path / "notes.log"
            log.write_text("hello artifacts")
            testwarden_attach(log, kind="log")
        """
    )
    result = pytester.runpytest_inprocess()
    result.assert_outcomes(passed=1)
    client = fake_client.instances[0]
    assert client.artifacts == [(1, 0, "log", "notes.log")]


def test_parametrized_tests_are_distinct(pytester, fake_client):
    pytester.makepyfile(
        test_params="""
        import pytest

        @pytest.mark.parametrize("browser_name", ["chromium", "firefox"])
        def test_multi(browser_name):
            pass
        """
    )
    result = pytester.runpytest_inprocess()
    result.assert_outcomes(passed=2)
    client = fake_client.instances[0]
    ids = sorted(envelope["normalized_id"] for envelope in client.envelopes)
    assert ids == [
        "test_params.py::test_multi[chromium]",
        "test_params.py::test_multi[firefox]",
    ]
    assert client.envelopes[0]["extras"].get("browser") in ("chromium", "firefox")
