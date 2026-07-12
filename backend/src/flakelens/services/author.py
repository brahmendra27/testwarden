"""NL test-authoring agent.

A non-coder describes a test in plain English + gives a URL. The agent drives a
real browser to discover the page's actual selectors, writes a Playwright test,
runs it to prove it passes, and (if the project has a repo) opens a PR.

The browser is behind a small protocol so the agent loop is unit-testable with a
stub; the real Playwright driver is a thin adapter verified live.
"""
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from flakelens.config import settings
from flakelens.db import SessionLocal
from flakelens.models import AuthorJob, Project
from flakelens.services.autofix import MODEL
from flakelens.services.llm import make_client, model_kwargs
from flakelens.services.workspace import FixWorkspace, WorkspaceError

MAX_ITERATIONS = 30

# Collect the visible interactive elements + their best selector hints.
_SNAPSHOT_JS = r"""
() => {
  const sel = 'a,button,input,select,textarea,[role=button],[role=link],'
            + '[role=checkbox],[role=tab],[role=menuitem],[data-testid]';
  const els = [...document.querySelectorAll(sel)];
  const seen = new Set();
  const out = [];
  for (const el of els) {
    const rects = el.getClientRects();
    if (!rects.length) continue;
    const tag = el.tagName.toLowerCase();
    const name = (el.getAttribute('aria-label') || el.getAttribute('placeholder')
      || el.innerText || el.value || '').trim().replace(/\s+/g, ' ').slice(0, 60);
    const entry = {
      tag,
      type: el.getAttribute('type'),
      role: el.getAttribute('role'),
      testid: el.getAttribute('data-testid'),
      id: el.id || null,
      name,
    };
    const key = JSON.stringify(entry);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(entry);
    if (out.length >= 60) break;
  }
  return { title: document.title, url: location.href, elements: out };
}
"""

_TAG_ROLE = {"a": "link", "button": "button", "select": "combobox", "textarea": "textbox"}

# --- Cues: autonomous interstitial watchers -----------------------------------
# Cookie banners, consent modals and promo popups are the #1 reason an authored
# test that passed in the agent's browser flakes in CI (fresh profile = banner is
# back). The driver detects them after every navigation/click, dismisses them,
# and tells the agent what it did so the generated test handles them too.

_CUES_JS = r"""
() => {
  const dismissPat = /^(reject all|reject|decline|necessary( cookies)? only|no thanks|not now|maybe later|close|dismiss|got it|ok(ay)?|continue|i agree|agree|accept all|accept|allow all|allow|[x×✕✖╳])$/i;
  const cuePat = /cookie|consent|gdpr|privacy|banner|modal|popup|overlay|interstitial|newsletter|subscribe/i;
  const containers = new Set();
  for (const el of document.querySelectorAll('[role=dialog],[aria-modal="true"]')) containers.add(el);
  for (const el of document.querySelectorAll('div,section,aside')) {
    if (containers.size >= 8) break;
    if (!cuePat.test(el.id + ' ' + el.className)) continue;
    const st = getComputedStyle(el);
    if ((st.position === 'fixed' || st.position === 'sticky') && el.offsetHeight > 40) containers.add(el);
  }
  const out = [];
  for (const c of containers) {
    if (!c.getClientRects().length) continue;
    const buttons = [];
    for (const b of c.querySelectorAll('button,[role=button],a')) {
      const t = (b.getAttribute('aria-label') || b.innerText || '').trim().replace(/\s+/g, ' ');
      if (t && dismissPat.test(t) && !buttons.includes(t)) buttons.push(t.slice(0, 40));
    }
    if (!buttons.length) continue;
    const text = (c.innerText || '').slice(0, 300);
    const kind = /cookie|consent|gdpr/i.test(c.id + ' ' + c.className + ' ' + text)
      ? 'cookie-consent' : 'overlay';
    out.push({ kind, buttons: buttons.slice(0, 6) });
    if (out.length >= 3) break;
  }
  return out;
}
"""

# Dismissal preference: decline non-essential first (privacy-preserving), then
# neutral close, accept only as a last resort. Deterministic for tests.
_DISMISS_ORDER = [
    ("reject all", "reject", "decline", "necessary only", "necessary cookies only", "no thanks"),
    ("close", "dismiss", "not now", "maybe later", "got it", "ok", "okay",
     "x", "×", "✕", "✖", "╳"),
    ("accept all", "accept", "i agree", "agree", "allow all", "allow", "continue"),
]


def pick_dismissal(cues: list[dict]) -> tuple[str, str] | None:
    """Choose (kind, button_name) to dismiss the first actionable cue, or None."""
    for cue in cues:
        lowered = {b.lower(): b for b in cue.get("buttons", [])}
        for tier in _DISMISS_ORDER:
            for want in tier:
                if want in lowered:
                    return cue["kind"], lowered[want]
    return None


def format_cue_note(kind: str, button: str) -> str:
    """The line shown to the agent (and logged) when a cue was auto-dismissed."""
    return (
        f'[cue] Dismissed a {kind} interstitial via page.get_by_role("button", name="{button}").'
        " Your generated test MUST perform this dismissal right after page.goto(), or it will"
        " flake in CI where the banner reappears on a fresh profile."
    )


def suggest_locator(el: dict) -> str:
    """Best-practice Playwright locator for a snapshot element."""
    if el.get("testid"):
        return f'page.get_by_test_id("{el["testid"]}")'
    role = el.get("role")
    if not role:
        if el["tag"] == "input":
            role = "checkbox" if el.get("type") == "checkbox" else "textbox"
        else:
            role = _TAG_ROLE.get(el["tag"], "")
    name = el.get("name") or ""
    if role in ("button", "link", "textbox", "checkbox", "tab", "menuitem", "combobox") and name:
        return f'page.get_by_role("{role}", name="{name}")'
    if el.get("id"):
        return f'page.locator("#{el["id"]}")'
    if name:
        return f'page.get_by_text("{name}")'
    return f'page.locator("{el["tag"]}")'


def format_snapshot(data: dict) -> str:
    lines = [f'Page: "{data.get("title", "")}"  ({data.get("url", "")})',
             "Interactive elements (with suggested locators):"]
    for el in data.get("elements", []):
        label = el.get("name") or "(no text)"
        role = el.get("role") or el.get("tag")
        lines.append(f'- {role} "{label}"  →  {suggest_locator(el)}')
    if not data.get("elements"):
        lines.append("- (no interactive elements found)")
    return "\n".join(lines)


class BrowserSession(Protocol):
    def open_url(self, url: str) -> str: ...
    def snapshot(self) -> str: ...
    def click(self, selector: str) -> str: ...
    def fill(self, selector: str, value: str) -> str: ...
    def close(self) -> None: ...


class PlaywrightBrowser:
    """Real browser driver — a live page the agent explores to find selectors."""

    def __init__(self):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        self.page = self._browser.new_page()

    def open_url(self, url: str) -> str:
        self.page.goto(url, wait_until="domcontentloaded", timeout=20000)
        return self.snapshot()

    def _run_cues(self) -> list[str]:
        """Detect and dismiss interstitials (cookie banners, modals, promo popups).

        Up to 3 rounds — dismissing one overlay sometimes reveals another.
        Returns the notes to surface to the agent.
        """
        notes: list[str] = []
        for _ in range(3):
            try:
                choice = pick_dismissal(self.page.evaluate(_CUES_JS))
            except Exception:
                break
            if not choice:
                break
            kind, button = choice
            try:
                self.page.get_by_role("button", name=button, exact=True).first.click(timeout=3000)
            except Exception:
                try:
                    self.page.get_by_text(button, exact=True).first.click(timeout=3000)
                except Exception:
                    break
            self.page.wait_for_timeout(300)
            notes.append(format_cue_note(kind, button))
        return notes

    def snapshot(self) -> str:
        notes = self._run_cues()
        text = format_snapshot(self.page.evaluate(_SNAPSHOT_JS))
        return "\n".join(notes + [text]) if notes else text

    def click(self, selector: str) -> str:
        self.page.locator(selector).first.click(timeout=10000)
        self.page.wait_for_timeout(400)
        return self.snapshot()

    def fill(self, selector: str, value: str) -> str:
        self.page.locator(selector).first.fill(value, timeout=10000)
        return f"filled {selector}"

    def close(self) -> None:
        try:
            self._browser.close()
            self._pw.stop()
        except Exception:
            pass


SYSTEM_PROMPT = """You are FlakeLens's test-authoring agent. A user described a test in plain \
English and gave a starting URL. Produce ONE working Playwright + pytest test that verifies it.

Workflow:
1. open_url the starting URL and read the snapshot (it lists real, visible elements with \
suggested Playwright locators — prefer those exact locators).
2. If the behavior spans multiple steps (e.g. log in, then check a result), use click/fill to \
walk the flow, re-reading the snapshot after each step so you use selectors that actually exist.
3. write_test a single focused test file under tests/ using the pytest-playwright `page` fixture:
       from playwright.sync_api import Page, expect
       def test_<clear_name>(page: Page):
           page.goto("<the URL>")
           ...            # use the discovered locators
           expect(...).to_be_visible()   # a real, meaningful assertion
   Prefer get_by_role / get_by_label / get_by_test_id over brittle CSS. Assert the outcome the \
user actually described, not just that a click happened.
4. run_test to verify it passes. If it fails, read the error, fix the test (or re-explore), and \
run again until green.
5. Call finish with outcome "authored" and a one-line summary once the test passes. If the app \
can't be reached or the described behavior isn't possible, finish with outcome "cannot" and why.

Cues: the browser auto-dismisses interstitials (cookie banners, consent modals, promo popups) \
and reports each as a "[cue]" line in the snapshot. When you see one, replicate that exact \
dismissal at the top of your test (right after page.goto) before any other interaction — in CI \
the banner reappears on a fresh browser profile and would otherwise make the test flaky.

Keep the test minimal, deterministic, and readable — a junior engineer should understand it."""

TOOLS = [
    {"name": "open_url", "description": "Navigate the browser to a URL and return the page snapshot.",
     "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
    {"name": "snapshot", "description": "Re-read the current page's interactive elements.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "click", "description": "Click an element (Playwright selector) and return the new snapshot.",
     "input_schema": {"type": "object", "properties": {"selector": {"type": "string"}}, "required": ["selector"]}},
    {"name": "fill", "description": "Fill a form field (Playwright selector) with a value.",
     "input_schema": {"type": "object", "properties": {"selector": {"type": "string"}, "value": {"type": "string"}},
                      "required": ["selector", "value"]}},
    {"name": "write_test", "description": "Write the generated test file (path under tests/, e.g. tests/test_login.py).",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                      "required": ["path", "content"]}},
    {"name": "run_test", "description": "Run the written test with pytest to verify it passes.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "finish", "description": "End once the test is verified green (or cannot be authored).",
     "input_schema": {"type": "object",
                      "properties": {"outcome": {"type": "string", "enum": ["authored", "cannot"]},
                                     "summary": {"type": "string"}, "path": {"type": "string"}},
                      "required": ["outcome", "summary"]}},
]


def _preview(tool_input: dict) -> str:
    return ", ".join(f"{k}={str(v)[:60]!r}" for k, v in tool_input.items() if k != "content")[:180]


def run_author_agent(client, browser: BrowserSession, workspace: FixWorkspace, task: str, log) -> dict:
    """Manual tool loop over browser + workspace. Returns {outcome, summary, path}."""
    messages = [{"role": "user", "content": task}]
    for iteration in range(1, MAX_ITERATIONS + 1):
        response = client.messages.create(
            **model_kwargs(max_tokens=6000),
            system=SYSTEM_PROMPT, tools=TOOLS, messages=messages,
        )
        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            text = "\n".join(b.text for b in response.content if b.type == "text")
            return {"outcome": "gave_up", "summary": text or "Agent stopped.", "path": None}
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for tool in tool_uses:
            if tool.name == "finish":
                log(f"[{iteration}] finish({tool.input.get('outcome')})")
                return {"outcome": tool.input.get("outcome", "authored"),
                        "summary": tool.input.get("summary", ""),
                        "path": tool.input.get("path")}
            log(f"[{iteration}] {tool.name}({_preview(tool.input)})")
            try:
                results.append({"type": "tool_result", "tool_use_id": tool.id,
                                "content": _dispatch(browser, workspace, tool.name, tool.input)})
            except Exception as exc:
                results.append({"type": "tool_result", "tool_use_id": tool.id,
                                "content": f"Error: {exc}", "is_error": True})
        messages.append({"role": "user", "content": results})
    return {"outcome": "gave_up", "summary": f"Stopped after {MAX_ITERATIONS} iterations.", "path": None}


def _dispatch(browser: BrowserSession, workspace: FixWorkspace, name: str, tool_input: dict) -> str:
    if name == "open_url":
        return browser.open_url(tool_input["url"])
    if name == "snapshot":
        return browser.snapshot()
    if name == "click":
        return browser.click(tool_input["selector"])
    if name == "fill":
        return browser.fill(tool_input["selector"], tool_input["value"])
    if name == "write_test":
        return workspace.write_file(tool_input["path"], tool_input["content"])
    if name == "run_test":
        return workspace.run_tests(f'{tool_input["path"]} --browser chromium -x')
    raise WorkspaceError(f"Unknown tool {name}")


def _slug(text: str, limit: int = 40) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:limit] or "test"


def execute_author_job(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.get(AuthorJob, job_id)

        def log(line: str) -> None:
            job.log = (job.log or "") + line + "\n"
            db.commit()

        browser = None
        try:
            project = db.get(Project, job.project_id)
            job.status = "running"
            job.model = MODEL
            db.commit()

            workdir = Path(settings.artifact_dir).parent / "agent-workspaces" / f"author-{job.id}"
            if workdir.exists():
                shutil.rmtree(workdir, ignore_errors=True)
            workspace = FixWorkspace(project.repo_url or "(generated)", workdir)
            base_branch = "main"
            if project.repo_url:
                log(f"Cloning {project.repo_url} ...")
                workspace.clone()
                base_branch = workspace.default_branch()
                branch = f"flakelens/author-{_slug(job.description)}-{job.id}"
                workspace.create_branch(branch)
                job.branch = branch
            else:
                workspace.init_empty()

            log("Launching browser ...")
            browser = PlaywrightBrowser()
            task = (
                f"User's request: {job.description}\n"
                f"Starting URL: {job.url}\n\n"
                "Author and verify the test."
            )
            client = make_client()
            log(f"Starting author agent ({MODEL}) ...")
            started = time.monotonic()
            verdict = run_author_agent(client, browser, workspace, task, log)
            log(f"Agent finished in {time.monotonic() - started:.0f}s: {verdict['outcome']}")

            test_files = workspace.list_files("test_*.py") + workspace.list_files("*_test.py")
            code = "\n\n".join(
                f"# ===== {p} =====\n{workspace.read_file(p)}" for p in sorted(set(test_files))
            )
            job.code = code or None
            job.summary = verdict["summary"]
            job.file_path = verdict.get("path")
            job.verified = verdict["outcome"] == "authored"

            if not job.verified or not code:
                job.status = "failed"
                job.error = verdict["summary"] or "No verified test produced"
            else:
                if project.repo_url:
                    workspace.commit(f"test: {job.description[:60]} (FlakeLens author #{job.id})")
                    token = os.environ.get("FLAKELENS_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")
                    if token and workspace.github_repo():
                        job.pr_url = workspace.push_and_open_pr(
                            job.branch, base_branch,
                            f"[FlakeLens] New test: {job.description[:60]}",
                            f"{verdict['summary']}\n\n🤖 Authored by the FlakeLens test-authoring agent.",
                            token,
                        )
                        log(f"Pull request opened: {job.pr_url}")
                    else:
                        log("No GitHub token / remote - test left on local branch; code shown below.")
                job.status = "completed"
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)[:2000]
            log(f"ERROR: {exc}")
        finally:
            if browser is not None:
                browser.close()
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()
