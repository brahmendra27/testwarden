"""Record a simple flow walkthrough of FlakeLens as an animated GIF.

Drives the running dashboard with Playwright, captures a few frames per page,
and stitches them into docs/media/flakelens-demo.gif. Repeatable — run it any
time the dev servers are up (frontend :5173, backend :8787).

    .\.venv\Scripts\python scripts\record_demo.py

Not a substitute for a narrated screen recording, but a zero-effort shareable
loop for a README / social post.
"""
from __future__ import annotations

import io
import time
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

BASE = "http://localhost:5173"
SLUG = "demo-web"
OUT = Path(__file__).resolve().parent.parent / "docs" / "media" / "flakelens-demo.gif"

WIDTH, HEIGHT = 1280, 820
SCALE_W = 900                      # downscale for a sane GIF file size
HOLD_MS = 1600                     # how long each page lingers
FRAME_MS = 200                     # per-GIF-frame duration

# (url, wait-for selector or None, caption for logging)
STEPS = [
    (f"{BASE}/", "text=Projects", "Projects — pass-rate sparkline, flaky badge"),
    (f"{BASE}/p/{SLUG}/overview", "text=/grade/i", "Overview — health grade + what to do today"),
    (f"{BASE}/p/{SLUG}/runs", None, "Runs — one strip per run, a segment per test"),
    (f"{BASE}/p/{SLUG}/runs/34", None, "Run detail — failures, verdict, SelfHeal"),
    (f"{BASE}/p/{SLUG}/flaky", None, "Flaky — ranked by score"),
    (f"{BASE}/p/{SLUG}/incidents", None, "Incidents — many failures, one root cause"),
    (f"{BASE}/p/{SLUG}/author", None, "Write a test in plain English (AI)"),
]


def grab(page) -> Image.Image:
    png = page.screenshot(type="png")
    img = Image.open(io.BytesIO(png)).convert("RGB")
    h = round(img.height * SCALE_W / img.width)
    return img.resize((SCALE_W, h), Image.LANCZOS)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    hold_frames = max(1, HOLD_MS // FRAME_MS)
    frames: list[Image.Image] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT},
                                device_scale_factor=1)
        for url, wait, caption in STEPS:
            print(f"  -> {caption}")
            page.goto(url, wait_until="networkidle")
            if wait:
                try:
                    page.wait_for_selector(wait, timeout=4000)
                except Exception:
                    pass
            time.sleep(0.6)                       # let charts/animation settle
            shot = grab(page)
            frames.extend([shot] * hold_frames)   # hold this page
        browser.close()

    if not frames:
        raise SystemExit("no frames captured")

    frames[0].save(
        OUT, save_all=True, append_images=frames[1:],
        duration=FRAME_MS, loop=0, optimize=True, disposal=2,
    )
    mb = OUT.stat().st_size / 1_048_576
    print(f"\nSaved {OUT}  ({len(frames)} frames, {mb:.1f} MB)")


if __name__ == "__main__":
    main()
