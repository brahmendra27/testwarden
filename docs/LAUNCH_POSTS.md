# Phase-1 launch posts — QA communities, feedback first

Ready-to-paste drafts. Rules that make these work: lead with the problem, not the
product; ask for feedback, don't pitch; reply to every comment within the first
2 hours (that's what keeps a post alive); never post the same text twice —
communities notice.

Links used everywhere:
- Live demo: https://flakelens-demo.onrender.com/
- GitHub: https://github.com/brahmendra27/testwarden
- PyPI: https://pypi.org/project/pytest-flakelens/

Suggested order: Playwright Discord first (fastest, friendliest signal), Reddit
next day, Ministry of Testing after that. Space them out — you want capacity to
respond, and each round's feedback improves the next post.

---

## 1. Reddit — r/QualityAssurance (also fits r/softwaretesting)

**Title:**
> I got tired of tools that only *tell* me a test is flaky, so I built one that tries to fix it. Would love brutal feedback.

**Body:**

> QA engineer here. Every flaky-test tool I've used ends at a dashboard: "this
> test is flaky, 47% failure rate, good luck." The retry-until-green culture
> that follows is how test suites quietly rot.
>
> So I built FlakeLens, a self-hosted test observability platform that tries to
> close the loop instead of just observing it:
>
> - **Detects** flaky tests (cross-run flip rate + within-run retry recoveries)
> - **Reproduces** them deterministically — it re-runs the test under controlled
>   chaos (network latency/failures, CPU throttle, timing jitter, seeded clock)
>   and bisects to the minimal condition that makes it fail. No more "can't repro".
> - **Fixes** them — an AI agent diagnoses the failure, patches the test, verifies
>   it passes *under the reproduced failure condition*, and opens a PR
> - **Quarantines** chronic flakes so CI stays green while fixes happen in the
>   background, and gives a merge verdict that ignores known-flaky noise
>
> It ingests Playwright/pytest natively and JUnit XML from anything else
> (Selenium, Cypress, Jest...). Self-hosted, open source, single Docker image.
>
> Clickable demo (no signup, seeded data): https://flakelens-demo.onrender.com/
> Code: https://github.com/brahmendra27/testwarden
>
> Honest questions for people who fight flaky tests for a living:
> 1. Would you trust an AI-authored fix to a test if it came as a reviewable PR?
> 2. Is deterministic reproduction actually valuable to you, or do you just
>    delete/quarantine and move on?
> 3. What would stop you from adopting something like this?
>
> Tear it apart. I'd rather hear it now than after I've built more.

---

## 2. Ministry of Testing (Club forum — "Tools" or "Show and tell")

MoT skews thoughtful/craft-oriented — lead with the testing philosophy question,
not the tool.

**Title:**
> Is "auto-fixing" flaky tests a good idea? I built it, and now I'm not sure — come argue with me

**Body:**

> I've spent years on teams where the flaky-test workflow was: notice → retry →
> mutter → eventually delete the test. The tooling never went further than
> *reporting* flakiness, so I built the thing I wished existed, and I'd genuinely
> like this community's view on whether the premise is sound.
>
> FlakeLens is a self-hosted test observability platform with three opinionated
> moves beyond the usual dashboards:
>
> 1. **Deterministic reproduction.** Instead of shrugging at "passes locally," it
>    re-runs a flaky test under controlled perturbations (network chaos, CPU
>    throttle, timing jitter, frozen clock) and searches for the minimal recipe
>    that makes it fail reliably. Flakiness becomes a reproducible bug report.
> 2. **AI-authored fixes as PRs.** An agent diagnoses the failure, patches the
>    test, and must prove the fix passes under that reproduced failure condition
>    before a human ever reviews the PR.
> 3. **A quarantine-and-heal loop.** Chronic flakes get quarantined (CI goes
>    green, but they keep reporting data), healed in the background, and released
>    when they're stable again.
>
> The tension I keep chewing on: a flaky test is often a *symptom* — of a race
> condition in the app, bad test design, or environment debt. Auto-fixing the
> test could paper over a real bug. My current answer is the classifier routes
> "app bug" and "environment" failures to humans and only heals genuine test
> bugs — but I don't fully trust classification either.
>
> Demo with seeded data (no signup): https://flakelens-demo.onrender.com/
> Source: https://github.com/brahmendra27/testwarden
>
> So: where should the line be between tooling that *informs* humans and tooling
> that *acts*? Has anyone here let automation modify their test code, and how
> did it go?

---

## 3. Playwright Discord (#show-and-tell or equivalent)

Discord wants short, concrete, and native to their tool. No wall of text.

> Built something for the Playwright+pytest folks: **FlakeLens** — self-hosted
> test observability where the interesting part isn't the dashboards, it's that
> it *acts*:
>
> 🔬 **Reproduces flakes deterministically** — reruns a test under controlled
> network/CPU/timing chaos (via CDP + route interception) and bisects to the
> minimal failure recipe
> 🩹 **SelfHeal** — AI agent diagnoses a failing test, fixes it, verifies green
> *under that recipe*, opens a PR
> ✍️ **Plain-English test authoring** — describe a flow, the agent drives your
> real app, writes the test with `get_by_role`/`get_by_test_id` locators, and
> proves it passes before showing you the code
>
> `pip install pytest-flakelens` streams results + traces/screenshots during the
> run; quarantined flakes auto-xfail so CI stays green.
>
> Live demo (seeded, no signup): https://flakelens-demo.onrender.com/
> Repo: https://github.com/brahmendra27/testwarden
>
> Very early — would love feedback from people running big Playwright suites.
> What's missing? What's wrong?

---

## Posting checklist

- [ ] Render demo is awake right before posting (free tier sleeps — open the URL
      yourself ~5 min before, or upgrade to the $7 instance for launch week)
- [ ] Reply to every early comment — first 2 hours decide the post's fate
- [ ] Note recurring feedback verbatim in an issues list; it feeds phase 2
- [ ] Don't argue with criticism — "fair point, noted" wins the room
- [ ] After ~1 week of feedback: decide on the video + Show HN / LinkedIn / PH

## What NOT to do

- Don't cross-post the same day (looks like a spam campaign)
- Don't use marketing language ("revolutionary", "game-changer") — these
  communities are allergic to it
- Don't hide that AI wrote fixes — it's the differentiator *and* the controversy;
  own it and let the PR-review safety story carry it
