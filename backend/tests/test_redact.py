from flakelens.services.redact import scrub

PLACEHOLDER = "«redacted»"


def test_scrubs_bearer_and_basic_auth():
    assert PLACEHOLDER in scrub("Authorization: Bearer abc123def456ghi789")
    assert "abc123def456ghi789" not in scrub("Authorization: Bearer abc123def456ghi789")
    assert PLACEHOLDER in scrub("authorization=Basic dXNlcjpwYXNz")


def test_scrubs_provider_api_keys():
    for secret in [
        "sk-ant-api03-AbCdEf1234567890xyz",
        "sk-proj-ABCDEFGHIJKLMNOPQRSTUVWX",
        "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        "github_pat_ABCDEF1234567890abcdef",
        "flk_0123456789abcdef0123456789abcdef",
        "AKIAIOSFODNN7EXAMPLE",
        "xoxb-1234567890-abcdefghij",
        "sk_live_abcdefghij1234567890",
    ]:
        out = scrub(f"leaked key {secret} in the log")
        assert secret not in out, secret
        assert PLACEHOLDER in out


def test_scrubs_jwt():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    out = scrub(f"token was {jwt}")
    assert jwt not in out
    assert PLACEHOLDER in out


def test_scrubs_url_credentials():
    out = scrub("postgresql://admin:s3cr3tP4ss@db.internal:5432/prod")
    assert "s3cr3tP4ss" not in out
    assert "admin" in out  # username kept, password redacted
    assert "db.internal" in out


def test_scrubs_cookies():
    out = scrub("Cookie: session=abc123; token=xyz789")
    assert "abc123" not in out
    assert PLACEHOLDER in out


def test_scrubs_sensitive_key_value_pairs():
    assert "hunter2" not in scrub("password=hunter2")
    assert "topsecret" not in scrub('"api_key": "topsecret123"')
    assert "s3cret" not in scrub("CLIENT_SECRET = s3cret_value_here")


def test_does_not_over_redact_normal_evidence():
    """The whole point: a stack trace with no secrets must survive intact."""
    trace = (
        "AssertionError: Locator expected to be visible\n"
        "  at tests/test_login.py:42\n"
        "  waiting for locator('#submit-button')\n"
        "TimeoutError: exceeded 5000ms"
    )
    assert scrub(trace) == trace


def test_empty_input():
    assert scrub("") == ""
    assert scrub(None) == ""
