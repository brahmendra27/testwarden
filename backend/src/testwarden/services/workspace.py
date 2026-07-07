"""Git workspace for autonomous fix jobs.

Clones the project's repo (GitHub URL or local path) into an isolated
directory, gives the agent path-safe file access, and handles the
branch → commit → push → pull-request tail end.
"""
import os
import re
import subprocess
from pathlib import Path

GITHUB_RE = re.compile(r"github\.com[/:]([^/]+)/([^/.]+?)(?:\.git)?/?$")
TEST_ENV_OVERRIDES = {"TESTWARDEN_ENABLED": "false", "CI": "false"}


class WorkspaceError(RuntimeError):
    pass


def _run_git(args: list[str], cwd: Path, timeout: int = 300) -> str:
    result = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=timeout,
        encoding="utf-8", errors="replace",
    )
    if result.returncode != 0:
        raise WorkspaceError(f"git {' '.join(args)} failed: {result.stderr.strip()[:800]}")
    return result.stdout


class FixWorkspace:
    def __init__(self, repo_url: str, root: Path):
        self.repo_url = repo_url
        # Absolute paths are required: Windows CreateProcess rejects a relative
        # cwd, and git resolves a relative clone target against its own cwd.
        self.root = Path(root).resolve()
        self.repo_dir = self.root / "repo"

    # -- lifecycle -----------------------------------------------------------
    def clone(self, commit_sha: str | None = None) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        source = self.repo_url
        local = Path(source)
        if local.exists():
            source = str(local)
        _run_git(["clone", "--no-hardlinks", source, str(self.repo_dir)], cwd=self.root)
        if commit_sha:
            try:
                _run_git(["checkout", commit_sha], cwd=self.repo_dir)
            except WorkspaceError:
                pass  # commit not in history (e.g. seeded data) — stay on default branch

    def init_empty(self) -> None:
        """Fresh workspace with no source repo (e.g. generated API test suites)."""
        self.repo_dir.mkdir(parents=True, exist_ok=True)
        _run_git(["init", "-b", "main"], cwd=self.repo_dir)

    def default_branch(self) -> str:
        try:
            ref = _run_git(["symbolic-ref", "--short", "HEAD"], cwd=self.repo_dir).strip()
            return ref or "main"
        except WorkspaceError:
            return "main"

    def create_branch(self, name: str) -> None:
        _run_git(["checkout", "-b", name], cwd=self.repo_dir)

    # -- agent file access (path-safe) ----------------------------------------
    def _safe(self, rel_path: str) -> Path:
        path = (self.repo_dir / rel_path).resolve()
        repo = self.repo_dir.resolve()
        if path != repo and repo not in path.parents:
            raise WorkspaceError(f"Path escapes workspace: {rel_path}")
        return path

    def list_files(self, pattern: str, limit: int = 200) -> list[str]:
        matches = []
        for path in sorted(self.repo_dir.rglob(pattern)):
            if ".git" in path.parts or not path.is_file():
                continue
            matches.append(path.relative_to(self.repo_dir).as_posix())
            if len(matches) >= limit:
                break
        return matches

    def read_file(self, rel_path: str, max_bytes: int = 50_000) -> str:
        path = self._safe(rel_path)
        if not path.is_file():
            raise WorkspaceError(f"File not found: {rel_path}")
        data = path.read_text(encoding="utf-8", errors="replace")
        if len(data) > max_bytes:
            return data[:max_bytes] + f"\n... [truncated, {len(data)} bytes total]"
        return data

    def edit_file(self, rel_path: str, old_str: str, new_str: str) -> str:
        path = self._safe(rel_path)
        content = path.read_text(encoding="utf-8")
        count = content.count(old_str)
        if count == 0:
            raise WorkspaceError("old_str not found in file")
        if count > 1:
            raise WorkspaceError(f"old_str appears {count} times; provide more context")
        path.write_text(content.replace(old_str, new_str, 1), encoding="utf-8")
        return f"Edited {rel_path}"

    def write_file(self, rel_path: str, content: str) -> str:
        path = self._safe(rel_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"Wrote {rel_path} ({len(content)} bytes)"

    def run_tests(
        self, args: str, cwd: str = ".", timeout: int = 300,
        extra_env: dict[str, str] | None = None,
    ) -> str:
        import shlex
        import sys

        workdir = self._safe(cwd)
        env = {**os.environ, **TEST_ENV_OVERRIDES, **(extra_env or {})}
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", *shlex.split(args), "-q", "--no-header"],
                cwd=str(workdir), capture_output=True, text=True, timeout=timeout, env=env,
                encoding="utf-8", errors="replace",
            )
        except subprocess.TimeoutExpired:
            return "TIMEOUT: test run exceeded time limit"
        output = (result.stdout or "") + "\n" + (result.stderr or "")
        if len(output) > 8000:
            output = output[:2000] + "\n... [truncated] ...\n" + output[-6000:]
        return f"exit code: {result.returncode}\n{output.strip()}"

    # -- outcome -------------------------------------------------------------
    def diff(self) -> str:
        _run_git(["add", "-A"], cwd=self.repo_dir)
        return _run_git(["diff", "--cached"], cwd=self.repo_dir)

    def commit(self, message: str) -> None:
        _run_git(["add", "-A"], cwd=self.repo_dir)
        _run_git(
            ["-c", "user.name=TestWarden Agent", "-c", "user.email=agent@testwarden.local",
             "commit", "-m", message],
            cwd=self.repo_dir,
        )

    def github_repo(self) -> tuple[str, str] | None:
        match = GITHUB_RE.search(self.repo_url)
        return (match.group(1), match.group(2)) if match else None

    def push_and_open_pr(
        self, branch: str, base: str, title: str, body: str, token: str
    ) -> str:
        import httpx

        repo = self.github_repo()
        if repo is None:
            raise WorkspaceError("repo_url is not a GitHub URL; cannot open PR")
        owner, name = repo
        push_url = f"https://x-access-token:{token}@github.com/{owner}/{name}.git"
        _run_git(["push", "--force-with-lease", push_url, f"HEAD:refs/heads/{branch}"],
                 cwd=self.repo_dir)
        response = httpx.post(
            f"https://api.github.com/repos/{owner}/{name}/pulls",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            json={"title": title, "head": branch, "base": base, "body": body},
            timeout=30,
        )
        if response.status_code == 422 and "already exists" in response.text:
            listing = httpx.get(
                f"https://api.github.com/repos/{owner}/{name}/pulls",
                params={"head": f"{owner}:{branch}", "state": "open"},
                headers={"Authorization": f"Bearer {token}"},
                timeout=30,
            )
            pulls = listing.json()
            if pulls:
                return pulls[0]["html_url"]
        response.raise_for_status()
        return response.json()["html_url"]
