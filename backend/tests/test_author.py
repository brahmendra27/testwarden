"""Offline tests for the NL test-authoring agent: pure locator/snapshot logic,
the loop with a stub browser + fake Claude, and the endpoints."""
import uuid
from types import SimpleNamespace

from flakelens.services.author import (
    format_cue_note,
    format_snapshot,
    pick_dismissal,
    run_author_agent,
    suggest_locator,
)
from flakelens.services.workspace import FixWorkspace


def test_suggest_locator_prefers_testid():
    assert suggest_locator({"tag": "li", "testid": "product", "name": "Widget"}) == \
        'page.get_by_test_id("product")'


def test_suggest_locator_role_and_name():
    assert suggest_locator({"tag": "button", "name": "Sign in"}) == \
        'page.get_by_role("button", name="Sign in")'
    # input -> textbox role
    assert suggest_locator({"tag": "input", "type": "text", "name": "Username"}) == \
        'page.get_by_role("textbox", name="Username")'
    # anchor -> link role
    assert suggest_locator({"tag": "a", "name": "Products"}) == \
        'page.get_by_role("link", name="Products")'


def test_suggest_locator_falls_back_to_id_then_text():
    assert suggest_locator({"tag": "div", "id": "banner", "name": ""}) == 'page.locator("#banner")'
    assert suggest_locator({"tag": "span", "name": "Hello"}) == 'page.get_by_text("Hello")'


def test_format_snapshot():
    data = {"title": "Store", "url": "http://x/", "elements": [
        {"tag": "button", "name": "Sign in"},
        {"tag": "input", "type": "text", "name": "Username", "id": "username"},
    ]}
    out = format_snapshot(data)
    assert 'Page: "Store"' in out
    assert 'get_by_role("button", name="Sign in")' in out
    assert "Username" in out


def test_pick_dismissal_prefers_decline_over_accept():
    cues = [{"kind": "cookie-consent", "buttons": ["Accept all", "Reject all", "Settings"]}]
    assert pick_dismissal(cues) == ("cookie-consent", "Reject all")


def test_pick_dismissal_neutral_close_before_accept():
    cues = [{"kind": "overlay", "buttons": ["Accept", "Close"]}]
    assert pick_dismissal(cues) == ("overlay", "Close")


def test_pick_dismissal_accepts_as_last_resort_and_case_insensitive():
    assert pick_dismissal([{"kind": "cookie-consent", "buttons": ["ACCEPT ALL"]}]) == \
        ("cookie-consent", "ACCEPT ALL")


def test_pick_dismissal_none_when_no_actionable_button():
    assert pick_dismissal([]) is None
    assert pick_dismissal([{"kind": "overlay", "buttons": ["Learn more"]}]) is None


def test_format_cue_note_tells_agent_to_replicate():
    note = format_cue_note("cookie-consent", "Reject all")
    assert note.startswith("[cue]")
    assert 'get_by_role("button", name="Reject all")' in note
    assert "goto" in note  # instructs placement right after page.goto


class FakeBrowser:
    """Stub browser: canned snapshots, records interactions."""

    def __init__(self):
        self.actions = []

    def open_url(self, url):
        self.actions.append(("open", url))
        return 'Page: "Login"\n- button "Sign in" → page.get_by_role("button", name="Sign in")'

    def snapshot(self):
        return "snapshot"

    def click(self, selector):
        self.actions.append(("click", selector))
        return "clicked"

    def fill(self, selector, value):
        self.actions.append(("fill", selector, value))
        return "filled"

    def close(self):
        pass


GENERATED = '''from playwright.sync_api import Page, expect

def test_login(page: Page):
    page.goto("http://example.test/")
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_text("Welcome")).to_be_visible()
'''


class FakeClient:
    """Scripted: open the page, write the test, run it, finish."""

    def __init__(self):
        self.step = 0
        self.messages = SimpleNamespace(create=self._create)

    def _b(self, name, inp):
        return SimpleNamespace(type="tool_use", id=f"toolu_{uuid.uuid4().hex[:6]}", name=name, input=inp)

    def _create(self, **kwargs):
        assert kwargs["system"].startswith("You are FlakeLens's test-authoring agent")
        script = [
            [self._b("open_url", {"url": "http://example.test/"})],
            [self._b("write_test", {"path": "tests/test_login.py", "content": GENERATED})],
            [self._b("run_test", {"path": "tests/test_login.py"})],
            [self._b("finish", {"outcome": "authored", "summary": "Login test authored.",
                                "path": "tests/test_login.py"})],
        ]
        content = script[self.step]
        self.step += 1
        return SimpleNamespace(content=content, stop_reason="tool_use")


def test_author_loop_with_stubs(tmp_path, monkeypatch):
    ws = FixWorkspace("(generated)", tmp_path / "w")
    ws.init_empty()
    # Don't actually run pytest/playwright in a unit test — stub the verify step.
    monkeypatch.setattr(ws, "run_tests", lambda *a, **k: "exit code: 0\n1 passed")
    browser = FakeBrowser()
    log = []
    verdict = run_author_agent(FakeClient(), browser, ws, "Test that a user can log in", log.append)

    assert verdict["outcome"] == "authored"
    assert verdict["path"] == "tests/test_login.py"
    assert ("open", "http://example.test/") in browser.actions
    assert "get_by_role" in ws.read_file("tests/test_login.py")
    assert any("write_test" in line for line in log)


def test_author_endpoints(client, project_key, monkeypatch):
    project, _ = project_key

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert client.post(f"/api/v1/projects/{project.slug}/author",
                       json={"description": "log in works", "url": "http://x"}).status_code == 503

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    executed = []
    monkeypatch.setattr("flakelens.api.author.execute_author_job", lambda jid: executed.append(jid))
    body = client.post(f"/api/v1/projects/{project.slug}/author",
                       json={"description": "log in works", "url": "http://x"}).json()
    assert body["status"] == "queued"
    assert executed == [body["id"]]

    latest = client.get(f"/api/v1/projects/{project.slug}/author").json()
    assert latest["job"]["id"] == body["id"]
    assert client.get(f"/api/v1/author-jobs/{body['id']}").json()["description"] == "log in works"

    # active job blocks a duplicate
    assert client.post(f"/api/v1/projects/{project.slug}/author",
                       json={"description": "another test", "url": "http://x"}).status_code == 409
