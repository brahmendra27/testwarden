from testwarden.services.stats import compute_case_stats, window_token


def entries(tokens, duration=1000):
    return [{"t": t, "d": duration, "r": i} for i, t in enumerate(tokens)]


def test_window_token_mapping():
    assert window_token("passed", False) == "P"
    assert window_token("passed", True) == "A"
    assert window_token("failed", False) == "F"
    assert window_token("error", False) == "E"
    assert window_token("skipped", False) is None
    assert window_token("xfailed", False) is None


def test_all_passing_is_not_flaky():
    stats = compute_case_stats(entries(["P"] * 10))
    assert stats["is_flaky"] is False
    assert stats["flake_score"] == 0.0


def test_always_failing_is_broken_not_flaky():
    stats = compute_case_stats(entries(["F"] * 10))
    assert stats["flip_count"] == 0
    assert stats["is_flaky"] is False


def test_flip_flopping_is_flaky():
    stats = compute_case_stats(entries(["P", "F", "P", "F", "P", "F", "P", "F"]))
    assert stats["flip_count"] == 7
    assert stats["is_flaky"] is True
    assert stats["flake_score"] >= 0.9


def test_intra_run_flaky_passes_are_flaky():
    # Passes every run, but half needed a retry.
    stats = compute_case_stats(entries(["P", "A", "P", "A", "P", "A", "P", "A"]))
    assert stats["is_flaky"] is True


def test_min_history_guard():
    stats = compute_case_stats(entries(["P", "F", "P"]))
    assert stats["flake_score"] > 0.3
    assert stats["is_flaky"] is False  # only 3 data points


def test_clean_streak_heals_flag():
    history = ["P", "F", "P", "F", "P", "F"] + ["P"] * 10
    stats = compute_case_stats(entries(history))
    assert stats["is_flaky"] is False


def test_single_regression_flip_not_flaky():
    # Passed 15 times then failed 5 times: one flip, a genuine regression.
    stats = compute_case_stats(entries(["P"] * 15 + ["F"] * 5))
    assert stats["flip_count"] == 1
    assert stats["is_flaky"] is False


def test_duration_stats():
    data = [{"t": "P", "d": d, "r": i} for i, d in enumerate([100, 200, 300, 400, 500])]
    stats = compute_case_stats(data)
    assert stats["avg_duration_ms"] == 300
    assert stats["p95_duration_ms"] == 500
