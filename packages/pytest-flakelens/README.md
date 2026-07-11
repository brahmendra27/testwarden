# pytest-flakelens

The pytest reporter for [FlakeLens](https://github.com/brahmendra27/testwarden) — a
self-hosted test observability platform with AI agents that **fix** flaky tests, not just
flag them.

This plugin streams your test results, retries, and Playwright artifacts (screenshots,
traces) to a FlakeLens server as the run happens. It never fails your test session: if the
server is unreachable, it logs one warning and gets out of the way.

## Install

```bash
pip install pytest-flakelens
```

## Use

Point it at your FlakeLens server and give it a project key (create a project in the
FlakeLens dashboard to get one):

```ini
# pytest.ini  (or [tool.pytest.ini_options] in pyproject.toml)
[pytest]
flakelens_url = https://flakelens.your-company.com
```

```bash
export FLAKELENS_API_KEY=flk_your_project_key
pytest
```

That's it — every run now appears in your dashboard with run history, flaky-test scoring,
failure records, and the AI analysis / auto-fix agents.

### Recommended options (Playwright)

```ini
addopts = --screenshot only-on-failure --tracing retain-on-failure --reruns 2
```

Failure screenshots and Playwright traces are captured automatically; `--reruns` (via
`pytest-rerunfailures`) feeds intra-run flaky detection.

## Configuration

| Setting (`pytest.ini`) | Env var | Default |
|---|---|---|
| `flakelens_url` | `FLAKELENS_URL` | — |
| `flakelens_api_key` | `FLAKELENS_API_KEY` | — |
| `flakelens_enabled` | `FLAKELENS_ENABLED` | `auto` (on when url + key are set) |
| `flakelens_framework` | `FLAKELENS_FRAMEWORK` | auto-detected |
| `flakelens_batch_size` | `FLAKELENS_BATCH_SIZE` | `20` |
| `flakelens_upload_artifacts` | `FLAKELENS_UPLOAD_ARTIFACTS` | `true` |

Branch/commit metadata is auto-read from `GITHUB_*` in CI (or set `FLAKELENS_BRANCH` /
`FLAKELENS_COMMIT`).

### Markers

- `@pytest.mark.quarantine` — FlakeLens-managed: runs the test as a non-strict xfail so a
  known-flaky test stops blocking CI while the fix agent works on it, while still reporting
  its real pass/fail.

### Attach files

```python
def test_thing(testwarden_attach):
    testwarden_attach("path/to/file.png", kind="screenshot")
```

## Not on pytest?

FlakeLens also ingests **JUnit XML** from any framework (Selenium/Java, Jest, Cypress, Go,
.NET…) via a single upload — see the FlakeLens docs.

## License

MIT
