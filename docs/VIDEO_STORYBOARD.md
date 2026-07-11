# Launch video storyboard (~75 seconds)

The single most shareable asset. Goal: land the two "magic moments" fast — an AI that
**writes** tests from English and **fixes** flaky ones — bookended by the dashboard.

Run `scripts/showcase.ps1` first to get a clean, repeatable state. Record at 1080p, mouse
movements slow and deliberate. No talking head needed; on-screen captions + soft music work
better for sharing. Keep each beat tight — cut dead time in the agent runs (speed-ramp the
"thinking" pauses 2–4×).

## Beat sheet

| Time | Screen | On-screen caption |
|---|---|---|
| 0:00–0:05 | Overview page: the **Health grade (A–F)** and **"What should I do today?"** list | *"Your test suite, graded — with a plain-English to-do list."* |
| 0:05–0:08 | Quick pan over run strips / flaky page | *"Flaky detection, history, incidents — the observability you'd expect."* |
| 0:08–0:12 | Click **Write a test (AI)** | *"But here's what's different."* |
| 0:12–0:30 | Type the English sentence + URL → **Write my test**. Show the log: open_url → fill → click → write → run → **✓ verified green** + the generated code | *"Describe a test in plain English. The agent drives your real app, writes it, and proves it passes."* |
| 0:30–0:34 | Cut to a red run → open a failure | *"When a test breaks…"* |
| 0:34–0:52 | **✨ Analyze** (root cause + classification) → **🩹 Launch SelfHeal** → live log → the **diff** → PR link | *"…it doesn't just tell you. It fixes it — and opens a pull request."* |
| 0:52–1:05 | Quarantine board: quarantine a flaky test → the closed loop | *"Chronic flakes get quarantined so CI stays green, then healed in the background."* |
| 1:05–1:12 | Incidents page: many failures → one root cause | *"14 failures, one root cause — fix it once."* |
| 1:12–1:18 | Merge verdict badge on a run (merge-ready / blocked) | *"A merge verdict that ignores flaky noise."* |
| 1:18–1:25 | End card | **FlakeLens** · *"Every tool tells you a test is flaky. FlakeLens fixes it."* · repo URL |

## The 30-second cut (for Twitter/LinkedIn autoplay)

Just 0:08→0:30 (author agent) + 0:30→0:52 (SelfHeal) + end card. The two magic moments and
the tagline. Lead with motion in the first 2 seconds (the agent already typing) — autoplay
feeds are won or lost in the first 2 seconds.

## Copy for the posts

- **Hook:** "Every tool tells you a test is flaky. I built one that fixes them."
- **Body:** what it does in 2 lines (observability + AI agents that write and fix tests),
  that it's open-source and self-hosted, and a clear ask: "Would love brutal feedback."
- **CTA:** the hosted demo link (people click a link, not a repo) + the GitHub link.
