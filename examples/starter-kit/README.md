# FlakeLens starter kit

A clean **Page Object Model** Playwright + pytest suite, pre-wired for FlakeLens.
Copy this folder, point it at your app, rewrite the page objects — and every run
streams into your FlakeLens dashboard with flaky detection, artifacts, and the
AI agents ready to go.

```
starter-kit/
├── pages/            # one class per screen (base_page, login_page, catalog_page)
├── tests/            # intent-level tests that use the page objects
├── site/             # tiny bundled demo app so the kit runs offline out of the box
├── conftest.py       # fixtures: base_url, page objects, a `logged_in` precondition
├── pytest.ini        # Playwright + FlakeLens config, test markers
└── requirements.txt
```

## Run it as-is (offline)

```bash
pip install -r requirements.txt
pip install -e ../../packages/pytest-flakelens   # the FlakeLens reporter
playwright install chromium
pytest                      # runs against the bundled demo site
pytest -m smoke             # just the smoke tests (tags)
```

## Point it at your own app

1. **Set your URL** — no code change needed for the base URL:
   ```bash
   BASE_URL=https://staging.your-app.com pytest
   ```
2. **Rewrite the page objects** in `pages/` — replace the selectors and methods
   with your screens. Keep the pattern: one class per page, intent-level methods
   (`login`, `search`) instead of raw selectors in tests. When your UI changes,
   you edit one page class, not every test.
3. **Write tests** in `tests/` that read as behavior, leaning on fixtures like
   `logged_in` for common preconditions.

## Send results to FlakeLens

1. In the dashboard, **+ New project** → copy the ingestion key it shows once.
2. Set it and run:
   ```powershell
   $env:FLAKELENS_API_KEY = "flk_..."
   pytest
   ```
   (`flakelens_url` in `pytest.ini` already points at `http://localhost:8787`.)

Every run now appears under your project — run strips, per-test history, flaky
scores, failure screenshots/traces, and the ✨ analysis / 🔧 SelfHeal buttons on
any failure. Branch/commit metadata is auto-read from `GITHUB_*` in CI.

## Quarantine a flaky test

Add `@pytest.mark.quarantine` above a test (see the commented example in
`tests/test_catalog.py`). FlakeLens runs it as a non-strict xfail so CI stays
green, while still tracking its real pass/fail so the SelfHeal agent can fix and
release it later.
