# FlakeLens — single-image build. Node compiles the SPA, Python serves the API
# plus the built SPA, so the whole product runs from one container.

# --- Stage 1: build the frontend ---
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# --- Stage 2: python runtime ---
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FLAKELENS_STATIC_DIR=/app/static \
    FLAKELENS_ARTIFACT_DIR=/data/artifacts

WORKDIR /app

# git is needed by the SelfHeal / reproducer agents (clone/branch/commit).
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml backend/README.md* ./backend/
COPY backend/src ./backend/src
RUN pip install ./backend[postgres]

COPY --from=frontend /app/frontend/dist /app/static
COPY scripts/docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh && mkdir -p /data/artifacts

EXPOSE 8787
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "flakelens.main:app", "--host", "0.0.0.0", "--port", "8787"]
