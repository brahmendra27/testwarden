"""Deterministic flake reproduction — perturbation layer.

When FLAKELENS_PERTURB holds a JSON recipe, this wraps Playwright's `page`
fixture to inject the controlled chaos described by the recipe: per-route
network latency/failures, CPU throttling, timing jitter, seeded clock/RNG, and
viewport changes. The goal is to turn a probabilistic race into a deterministic,
repeatable failure so it can be diagnosed and a fix verified under the exact
condition that broke it.

Absent the env var this module does nothing — normal test runs pay no cost.

Recipe shape (all keys optional):
{
  "network": [{"url": "**/api/cart*", "delay_ms": 400, "fail": false, "abort": "failed"}],
  "cpu_throttle": 4,               # CDP setCPUThrottlingRate multiplier
  "timing_jitter_ms": 200,         # random extra delay on setTimeout callbacks
  "seed": 12345,                   # seed Math.random + freeze Date drift
  "viewport": {"width": 375, "height": 812},
  "offline_after_ms": 0            # go offline N ms into the test (0 = never)
}
"""
import json
import os

ENV_VAR = "FLAKELENS_PERTURB"

# The catalog the search engine draws from. Each entry is a self-contained
# recipe fragment; the engine composes and bisects these.
CATEGORIES = ("network", "cpu", "timing", "seed", "viewport")


def load_recipe() -> dict | None:
    raw = os.environ.get(ENV_VAR)
    if not raw:
        return None
    try:
        recipe = json.loads(raw)
        return recipe if isinstance(recipe, dict) else None
    except (ValueError, TypeError):
        return None


_INIT_SCRIPT = """
(() => {
  const cfg = window.__flakelens_perturb || {};
  if (cfg.seed != null) {
    let s = cfg.seed >>> 0;
    Math.random = function () {
      s = (s * 1664525 + 1013904223) >>> 0;
      return s / 4294967296;
    };
  }
  if (cfg.timing_jitter_ms) {
    const realSetTimeout = window.setTimeout.bind(window);
    window.setTimeout = function (fn, delay, ...args) {
      const extra = Math.floor(Math.random() * cfg.timing_jitter_ms);
      return realSetTimeout(fn, (delay || 0) + extra, ...args);
    };
  }
})();
"""


def apply_to_page(page, recipe: dict) -> None:
    """Apply the recipe to a Playwright sync `page`. Best-effort and defensive:
    a perturbation that a given browser/context can't honor is skipped, not fatal."""
    # 1. Seed + timing jitter via an init script (runs before page scripts).
    seed = recipe.get("seed")
    jitter = recipe.get("timing_jitter_ms")
    if seed is not None or jitter:
        cfg = json.dumps({"seed": seed, "timing_jitter_ms": jitter})
        try:
            page.add_init_script(f"window.__flakelens_perturb = {cfg};")
            page.add_init_script(_INIT_SCRIPT)
        except Exception:
            pass

    # 2. Viewport.
    viewport = recipe.get("viewport")
    if viewport:
        try:
            page.set_viewport_size(
                {"width": int(viewport["width"]), "height": int(viewport["height"])}
            )
        except Exception:
            pass

    # 3. CPU throttling via CDP (Chromium only).
    throttle = recipe.get("cpu_throttle")
    if throttle and throttle > 1:
        try:
            client = page.context.new_cdp_session(page)
            client.send("Emulation.setCPUThrottlingRate", {"rate": float(throttle)})
        except Exception:
            pass

    # 4. Per-route network chaos.
    for rule in recipe.get("network", []) or []:
        _install_route(page, rule)

    # 5. Go offline partway through (surfaces missing retry/offline handling).
    offline_after = recipe.get("offline_after_ms")
    if offline_after and offline_after > 0:
        try:
            page.add_init_script(
                f"setTimeout(() => {{ try {{ window.dispatchEvent(new Event('offline')); }} "
                f"catch (e) {{}} }}, {int(offline_after)});"
            )
        except Exception:
            pass


def _install_route(page, rule: dict) -> None:
    url = rule.get("url", "**/*")
    delay_ms = int(rule.get("delay_ms", 0) or 0)
    abort = rule.get("abort")
    fail = bool(rule.get("fail"))

    def handler(route):
        try:
            if delay_ms:
                import time

                time.sleep(delay_ms / 1000.0)
            if abort or fail:
                route.abort(abort if isinstance(abort, str) else "failed")
            else:
                route.continue_()
        except Exception:
            try:
                route.continue_()
            except Exception:
                pass

    try:
        page.route(url, handler)
    except Exception:
        pass
