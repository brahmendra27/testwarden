import json

from flakelens_reporter import perturb


def test_load_recipe_absent(monkeypatch):
    monkeypatch.delenv(perturb.ENV_VAR, raising=False)
    assert perturb.load_recipe() is None


def test_load_recipe_parses_json(monkeypatch):
    monkeypatch.setenv(perturb.ENV_VAR, json.dumps({"cpu_throttle": 4}))
    assert perturb.load_recipe() == {"cpu_throttle": 4}


def test_load_recipe_ignores_garbage(monkeypatch):
    monkeypatch.setenv(perturb.ENV_VAR, "not json {{{")
    assert perturb.load_recipe() is None
    monkeypatch.setenv(perturb.ENV_VAR, json.dumps([1, 2, 3]))  # not a dict
    assert perturb.load_recipe() is None


class FakePage:
    """Records the perturbations applied, tolerating any subset of the API."""

    def __init__(self):
        self.init_scripts = []
        self.routes = []
        self.viewport = None
        self.cdp_calls = []

    def add_init_script(self, script):
        self.init_scripts.append(script)

    def set_viewport_size(self, size):
        self.viewport = size

    def route(self, url, handler):
        self.routes.append(url)

    @property
    def context(self):
        page = self

        class Ctx:
            def new_cdp_session(self, _p):
                class Session:
                    def send(self, method, params):
                        page.cdp_calls.append((method, params))

                return Session()

        return Ctx()


def test_apply_to_page_dispatches_all_categories():
    page = FakePage()
    perturb.apply_to_page(page, {
        "seed": 42,
        "timing_jitter_ms": 100,
        "viewport": {"width": 375, "height": 812},
        "cpu_throttle": 4,
        "network": [{"url": "**/api/*", "delay_ms": 300}],
    })
    assert page.viewport == {"width": 375, "height": 812}
    assert page.routes == ["**/api/*"]
    assert any("setCPUThrottlingRate" in call[0] for call in page.cdp_calls)
    assert len(page.init_scripts) >= 2  # config + jitter/seed script


def test_apply_to_page_is_defensive():
    # A page missing most of the API should not raise.
    class Bare:
        def add_init_script(self, s):
            raise RuntimeError("nope")

    perturb.apply_to_page(Bare(), {"seed": 1, "network": [{"url": "*", "delay_ms": 1}]})
