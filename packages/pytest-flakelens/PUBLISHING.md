# Publishing pytest-flakelens to PyPI

The package is already built and validated (`twine check` passes). You just need to
run the final upload with your own PyPI account — that step can't be automated for you
because it requires your credentials.

## First, check the name is free

Open <https://pypi.org/project/pytest-flakelens/>. If it's a 404, the name is available.
If it's taken, change `name = "..."` in `pyproject.toml` (e.g. `flakelens-pytest`) and
rebuild.

## Option A — one-command manual upload (fastest)

1. Create a PyPI account at <https://pypi.org/account/register/> and an **API token** at
   <https://pypi.org/manage/account/token/> (scope: "Entire account" for the first upload).
2. From the package directory, build fresh and upload:

   ```powershell
   cd packages\pytest-flakelens
   ..\..\.venv\Scripts\python -m build
   ..\..\.venv\Scripts\python -m twine upload dist/*
   ```

   When prompted, username is `__token__` and password is the `pypi-…` token.
3. Verify: `pip install pytest-flakelens` in a fresh environment.

> Tip: test against **TestPyPI** first —
> `python -m twine upload --repository testpypi dist/*` then
> `pip install --index-url https://test.pypi.org/simple/ pytest-flakelens`.

## Option B — automated via GitHub Actions (recommended for repeat releases)

The repo ships `.github/workflows/publish-pypi.yml` using **Trusted Publishing** (no token
stored anywhere). One-time setup:

1. On PyPI: create the project's trusted publisher at
   `https://pypi.org/manage/project/pytest-flakelens/settings/publishing/`
   — GitHub repo `brahmendra27/testwarden`, workflow `publish-pypi.yml`, environment `pypi`.
   (For the very first release you may need to do one manual upload via Option A first, or
   use PyPI's "pending publisher" flow.)
2. In the GitHub repo, create an environment named `pypi` (Settings → Environments).
3. Release by pushing a tag:

   ```bash
   git tag reporter-v0.1.0
   git push origin reporter-v0.1.0
   ```

   The workflow builds and publishes automatically.

## Bumping versions

Edit `version = "..."` in `pyproject.toml`, commit, then tag `reporter-vX.Y.Z`. PyPI
rejects re-uploading an existing version, so always bump.
