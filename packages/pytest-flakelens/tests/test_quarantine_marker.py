def test_quarantine_marker_xfails_and_flags(pytester, fake_client):
    pytester.makepyfile(
        test_quarantined="""
        import pytest

        @pytest.mark.quarantine
        def test_still_broken():
            assert False  # still failing, but must not fail CI

        @pytest.mark.quarantine
        def test_now_healthy():
            assert True  # healed: reports as xpassed

        def test_normal():
            assert True
        """
    )
    result = pytester.runpytest_inprocess()
    # CI stays green: the quarantined failure is an xfail, not a failure.
    outcomes = result.parseoutcomes()
    assert outcomes.get("failed") is None
    assert outcomes.get("xfailed") == 1
    assert outcomes.get("xpassed") == 1

    envelopes = {e["title"]: e for e in fake_client.instances[0].envelopes}
    assert envelopes["test_still_broken"]["status"] == "xfailed"
    assert envelopes["test_still_broken"]["extras"].get("quarantined") is True
    assert envelopes["test_now_healthy"]["status"] == "xpassed"
    assert envelopes["test_now_healthy"]["extras"].get("quarantined") is True
    assert envelopes["test_normal"]["extras"].get("quarantined") is None
