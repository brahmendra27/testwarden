# FlakeLens

Self-hosted test automation observability platform (inspired by [kinora.dev](https://kinora.dev/)).
It ingests results from **Playwright + pytest** suites, tracks run history, records failures with
full context (stack traces, screenshots, Playwright traces), detects **flaky tests**, and compares runs.

## Features (v0.1 MVP)

- **Run history** — colored strip per run (one segment per test), pass-rate sparklines, duration trends
- **Stable test identity** — follow a single test run-to-run: when it started flaking, when it was fixed
- **Failure records** — per-attempt stack traces, stdout, inline screenshots, Playwright trace downloads
- **Flaky detection** — cross-run flip-flop rate *and* intra-run retry recoveries (pytest-rerunfailures aware)
- **Run comparison** — newly failing / fixed / newly flaky / still failing between any two runs
- **`pytest-flakelens` reporter** — streams results + artifacts during the run; never fails your session
- **Quarantine-and-heal loop** — quarantine a flaky test via an agent-authored PR
  (`@pytest.mark.quarantine` runs it as non-strict xfail, so CI goes green while it keeps
  reporting real outcomes), let SelfHeal fix it in the background, then release it with
  another PR once it posts a clean streak. The Quarantine page tracks the whole lifecycle.

## Architecture

```
backend/                    FastAPI + SQLAlchemy (SQLite by default, Postgres via docker-compose)
frontend/                   React + TypeScript + Vite + Tailwind dashboard
packages/pytest-flakelens/ pytest plugin that reports into the ingestion API
examples/sample-playwright-project/  offline demo suite (1 flaky + 1 broken test on purpose)
```

The result schema is framework-agnostic (envelope + `extras` JSON), so Selenium/JUnit XML
and API-test runners can be added as adapters without schema changes.

## Quickstart (Windows, no Docker)

```powershell
# 1. Install
python -m venv .venv
.\.venv\Scripts\pip install -e ".\backend[dev]" -e ".\packages\pytest-flakelens[dev]" pytest-playwright
.\.venv\Scripts\python -m playwright install chromium
cd frontend; npm install; cd ..

# 2. Seed demo data (prints the ingestion API key)
.\.venv\Scripts\python -m flakelens.seed

# 3. Run everything + the sample suite
.\scripts\demo.ps1
```

Open <http://localhost:5173>. The `demo-web` project has 30 seeded runs plus the run your
sample suite just reported — including an amber flaky test with retry attempts and a hard
failure with screenshot + trace.

Prefer Postgres? `docker compose up -d db` and set
`FLAKELENS_DATABASE_URL=postgresql+psycopg://flakelens:flakelens@localhost:5433/flakelens`
(install `backend[postgres]`).

## Report your own suite

```ini
# pytest.ini
[pytest]
addopts = --screenshot only-on-failure --tracing retain-on-failure --reruns 2
flakelens_url = http://localhost:8787
```

```powershell
pip install pytest-flakelens
$env:FLAKELENS_API_KEY = "flk_..."   # create a project + key, or use the seeded one
pytest
```

Branch/commit metadata is picked up from `FLAKELENS_BRANCH`/`FLAKELENS_COMMIT`
(or `GITHUB_*` vars automatically in GitHub Actions). Attach extra files with the
`flakelens_attach(path, kind="log")` fixture. Note: `pytest-xdist` is not supported yet.

## Tests

```powershell
cd backend; ..\.venv\Scripts\python -m pytest      # 20 tests: API, stats, compare
cd packages\pytest-flakelens; ..\..\.venv\Scripts\python -m pytest   # 7 plugin tests
```

## AI features

Both need `ANTHROPIC_API_KEY` set on the backend server (model: `claude-opus-4-8`).

- **AI failure analysis** — the ✨ button on any failure sends the stack trace, retry history
  and flake stats to Claude, which returns a root cause, a classification
  (APP_BUG / TEST_BUG / FLAKY_TIMING / ENVIRONMENT) and a suggested fix. Cached per result.
- **API test agent** — the "API test agent" page takes an OpenAPI spec URL + base URL and
  launches an agent that generates a pytest + httpx suite (RestAssured-style assertions:
  status codes, headers, body shapes, negative auth cases), verifies it against the live
  API, and reports the results into the dashboard as a `pytest-httpx` run. Never calls
  state-changing endpoints with valid data.
- **Auto-fix agent** — the 🔧 button launches an autonomous agent that clones the project's
  `repo_url` (GitHub URL or local path), locates the root cause with read/edit/run-tests
  tools, applies a minimal fix, re-runs the failing test to verify, commits to a
  `flakelens/fix-*` branch and — with `GITHUB_TOKEN` set — opens a pull request.
  Without a token the diff and branch are shown in the dashboard. Set the repo with
  `PATCH /api/v1/projects/{slug} {"repo_url": "..."}`.

## Roadmap

- **Selenium Java:** JUnit XML ingestion adapter translating into the same result envelope.
- Auto-quarantine suggestions, failure clustering by fingerprint, Slack digests.
