#!/usr/bin/env bash
# Wait for Postgres (if configured) before starting, so the app doesn't crash-loop
# on a cold `docker compose up`. Tables + additive columns are created on startup.
set -e

if [[ "${FLAKELENS_DATABASE_URL:-}" == postgres* ]]; then
  echo "Waiting for the database to accept connections..."
  python - <<'PY'
import os, time, sys
from sqlalchemy import create_engine, text

url = os.environ["FLAKELENS_DATABASE_URL"]
for attempt in range(60):
    try:
        create_engine(url).connect().execute(text("SELECT 1"))
        print("Database is ready.")
        sys.exit(0)
    except Exception as exc:
        print(f"  not ready ({attempt + 1}/60): {exc}")
        time.sleep(2)
print("Database never became ready.", file=sys.stderr)
sys.exit(1)
PY
fi

exec "$@"
