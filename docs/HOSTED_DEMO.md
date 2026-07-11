# Standing up a hosted FlakeLens demo

A public demo lets people click through the product without cloning anything — it's the
single highest-leverage launch asset. This sets up a **safe, zero-cost, self-reseeding**
demo.

## What "safe" means here

- **No `ANTHROPIC_API_KEY`** on the demo server → the AI agent buttons (SelfHeal, author,
  API agent, crew classify) render but show "requires a key" instead of running. This means
  **random visitors can't spend your API credits.** All the observability features — run
  history, flaky detection, incidents, health grade, quarantine board, cross-branch compare,
  merge verdict — work fully on the seeded data.
- **`FLAKELENS_SEED_ON_START=true`** → a fresh deploy auto-populates the demo project (30
  runs, flaky tests, a regression, incidents) so the dashboard looks alive immediately.
- **Ephemeral SQLite** → the DB resets on each redeploy, so the demo can't be polluted.

## Option A — Render (easiest, free tier)

The repo ships `render.yaml`. 

1. Push the repo to GitHub (done).
2. On <https://render.com> → **New → Blueprint** → pick the repo. Render reads `render.yaml`,
   builds the Docker image, and deploys. First build ~5–8 min.
3. Open the assigned `*.onrender.com` URL — the dashboard is live and seeded.

> Free-tier services sleep after inactivity and cold-start in ~30s. Fine for a demo; for a
> launch-day spike, bump to a paid instance so it stays warm.

## Option B — Fly.io / Railway / any Docker host

The image is a standard single container (`Dockerfile`). Set these env vars:

```
FLAKELENS_SEED_ON_START=true
FLAKELENS_DATABASE_URL=sqlite:////data/flakelens.db   # or a Postgres URL
FLAKELENS_SECURE_COOKIES=true
```

Expose the container's port (the app listens on `$PORT`, default 8787). Done.

## Making it a *private* demo (for a specific audience)

Set `FLAKELENS_ACCESS_TOKEN=some-token` and share the token. Viewers hit a login screen,
enter the token once, and get in. (On Render, uncomment the `generateValue` block in
`render.yaml`, then read the generated token from the dashboard.)

## Turning agents ON for a controlled demo

For a gated demo where you *want* to show SelfHeal/author live (e.g. a sales call), add
`ANTHROPIC_API_KEY` **and** `FLAKELENS_ACCESS_TOKEN` so only invited viewers can trigger the
(credit-spending) agents. Don't enable agents on a fully public demo.
