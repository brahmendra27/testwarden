"""The Reproducer: deterministically reproduce a flaky test.

Strategy (a ladder, cheapest first):
  0. Baseline — run the test unperturbed N times to measure its natural flake rate.
  1. Stress-all — run under every perturbation category at once. If it still
     never fails, the flake is likely infra/true-random → give up honestly.
  2. Category bisect — find which single categories, applied alone, raise the
     failure rate. Keep the ones that do.
  3. Minimize — within the winning categories, shrink to the smallest condition
     (e.g. the specific slow route, the lowest CPU throttle) that still fails.

Output: the minimal recipe + a human label + failure-rate stats. That recipe is
the marketable artifact — it turns "sometimes red" into "fails 10/10 when X".

The `plan_*` functions are pure (no browser, no I/O) so the ladder logic is
unit-tested directly; the executor feeds real run-results back into them.
"""
from __future__ import annotations

# Perturbation catalog. Each candidate is (category, recipe_fragment, label).
STRESS_ALL = {
    "network": [{"url": "**/*", "delay_ms": 400}],
    "cpu_throttle": 6,
    "timing_jitter_ms": 300,
    "seed": 999983,
    "viewport": {"width": 375, "height": 812},
}

CATEGORY_CANDIDATES: list[tuple[str, dict, str]] = [
    ("network", {"network": [{"url": "**/*", "delay_ms": 500}]}, "all requests +500ms latency"),
    ("cpu", {"cpu_throttle": 6}, "CPU throttled 6×"),
    ("timing", {"timing_jitter_ms": 300}, "setTimeout jitter up to 300ms"),
    ("viewport", {"viewport": {"width": 375, "height": 812}}, "mobile viewport 375×812"),
    ("seed", {"seed": 999983}, "seeded RNG/clock"),
]

# Minimization ladders per category: try progressively gentler conditions.
NETWORK_DELAYS = [500, 300, 200, 100]
CPU_RATES = [6, 4, 2]


def merge_recipes(fragments: list[dict]) -> dict:
    """Combine recipe fragments; network rules concatenate, scalars overwrite."""
    merged: dict = {}
    for fragment in fragments:
        for key, value in fragment.items():
            if key == "network":
                merged.setdefault("network", [])
                merged["network"].extend(value)
            else:
                merged[key] = value
    return merged


def is_repro(fail_rate: float, baseline: float, min_runs_ok: bool = True) -> bool:
    """A candidate reproduces if it fails clearly more than baseline and often
    enough to be useful (>= 60%), with a meaningful lift over the natural rate."""
    return min_runs_ok and fail_rate >= 0.6 and fail_rate - baseline >= 0.4


def label_recipe(recipe: dict) -> str:
    parts = []
    for rule in recipe.get("network", []) or []:
        if rule.get("abort") or rule.get("fail"):
            parts.append(f"{rule.get('url')} fails")
        elif rule.get("delay_ms"):
            parts.append(f"{rule.get('url')} +{rule['delay_ms']}ms")
    if recipe.get("cpu_throttle"):
        parts.append(f"CPU {recipe['cpu_throttle']}×")
    if recipe.get("timing_jitter_ms"):
        parts.append(f"timing jitter {recipe['timing_jitter_ms']}ms")
    if recipe.get("viewport"):
        vp = recipe["viewport"]
        parts.append(f"viewport {vp['width']}×{vp['height']}")
    if "seed" in recipe:
        parts.append(f"seed {recipe['seed']}")
    return " + ".join(parts) or "no perturbation"


def minimize_candidates(category: str) -> list[tuple[dict, str]]:
    """Ordered gentlest-last conditions to try shrinking a winning category to."""
    if category == "network":
        return [
            ({"network": [{"url": "**/*", "delay_ms": d}]}, f"all requests +{d}ms")
            for d in NETWORK_DELAYS
        ]
    if category == "cpu":
        return [({"cpu_throttle": r}, f"CPU throttled {r}×") for r in CPU_RATES]
    if category == "timing":
        return [({"timing_jitter_ms": 300}, "setTimeout jitter up to 300ms")]
    if category == "viewport":
        return [({"viewport": {"width": 375, "height": 812}}, "mobile viewport 375×812")]
    if category == "seed":
        return [({"seed": 999983}, "seeded RNG/clock")]
    return []
