# TestWarden

Self-hosted test automation observability platform (inspired by [kinora.dev](https://kinora.dev/)).
It ingests results from **Playwright + pytest** suites, tracks run history, records failures with
full context (stack traces, screenshots, Playwright traces), detects **flaky tests**, and compares runs.

## Features (v0.1 MVP)

- **Run history** — colored strip per run (one segment per test), pass-rate sparklines, duration trends
- **Stable test identity** — follow a single test run-to-run: when it started flaking, when it was fixed
- **Failure records** — per-attempt stack traces, stdout, inline screenshots, Playwright trace downloads
- **Flaky detection** — cross-run flip-flop rate *and* intra-run retry recoveries (pytest-rerunfailures aware)
- **Run comparison** — newly failing / fixed / newly flaky / still failing between any two runs
- **`pytest-testwarden` reporter** — streams results + artifacts during the run; never fails your session

## Architecture

```
backend/                    FastAPI + SQLAlchemy (SQLite by default, Postgres via docker-compose)
frontend/                   React + TypeScript + Vite + Tailwind dashboard
packages/pytest-testwarden/ pytest plugin that reports into the ingestion API
examples/sample-playwright-project/  offline demo suite (1 flaky + 1 broken test on purpose)
```

The result schema is framework-agnostic (envelope + `extras` JSON), so Selenium/JUnit XML
and API-test runners can be added as adapters without schema changes.

## Quickstart (Windows, no Docker)

```powershell
# 1. Install
python -m venv .venv
.\.venv\Scripts\pip install -e ".\backend[dev]" -e ".\packages\pytest-testwarden[dev]" pytest-playwright
.\.venv\Scripts\python -m playwright install chromium
cd frontend; npm install; cd ..

# 2. Seed demo data (prints the ingestion API key)
.\.venv\Scripts\python -m testwarden.seed

# 3. Run everything + the sample suite
.\scripts\demo.ps1
```

Open <http://localhost:5173>. The `demo-web` project has 30 seeded runs plus the run your
sample suite just reported — including an amber flaky test with retry attempts and a hard
failure with screenshot + trace.

Prefer Postgres? `docker compose up -d db` and set
`TESTWARDEN_DATABASE_URL=postgresql+psycopg://testwarden:testwarden@localhost:5433/testwarden`
(install `backend[postgres]`).

## Report your own suite

```ini
# pytest.ini
[pytest]
addopts = --screenshot only-on-failure --tracing retain-on-failure --reruns 2
testwarden_url = http://localhost:8787
```

```powershell
pip install pytest-testwarden
$env:TESTWARDEN_API_KEY = "twk_..."   # create a project + key, or use the seeded one
pytest
```

Branch/commit metadata is picked up from `TESTWARDEN_BRANCH`/`TESTWARDEN_COMMIT`
(or `GITHUB_*` vars automatically in GitHub Actions). Attach extra files with the
`testwarden_attach(path, kind="log")` fixture. Note: `pytest-xdist` is not supported yet.

## Tests

```powershell
cd backend; ..\.venv\Scripts\python -m pytest      # 20 tests: API, stats, compare
cd packages\pytest-testwarden; ..\..\.venv\Scripts\python -m pytest   # 7 plugin tests
```

## Roadmap

- **Phase 2 — auto-fix agent:** analyze a failure record (error + stack + screenshot + trace)
  with the Claude API, generate a patch in the test repo, open a PR for review.
  Hooks already in place: `failure_fingerprint`, `projects.repo_url`, `runs.commit_sha`.
- **Phase 3 — API-testing agent:** generate + execute REST API tests (pytest + httpx) from an
  OpenAPI spec, reporting through the same plugin (`framework="pytest-httpx"`).
- **Selenium Java:** JUnit XML ingestion adapter translating into the same result envelope.
