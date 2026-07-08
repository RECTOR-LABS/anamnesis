# Anamnesis runtime: ONE container serving the React dashboard (SPA) + the FastAPI seam.
# `uvicorn app.main:app` serves the built frontend at / and the forensic API at /api/*; the chat
# route spawns the forensic MCP server as a stdio child over the frozen engine. Multi-stage: a
# node stage builds frontend/dist, the python stage runs it.

# ── Stage 1: build the React dashboard ──────────────────────────────────────────────────────────
# node:24-slim matches the host (node 24 / npm 11) that generated package-lock.json and satisfies
# Vite 8's engines (^20.19 || >=22.12). package files first for a cacheable `npm ci` layer.
FROM node:24-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ── Stage 2: python runtime ─────────────────────────────────────────────────────────────────────
FROM python:3.12-slim

# soundfile (imported transitively by qwen_agent) needs libsndfile at runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# EDITABLE install is required, not optional: agent.py resolves mcp/solana_forensics_mcp.py
# relative to its own location (repo root), so the source must stay laid out as src/ + mcp/.
# The [api] extra adds fastapi/uvicorn/sse-starlette (pinned) on top of the engine deps.
COPY pyproject.toml ./
COPY src ./src
COPY mcp ./mcp
COPY scripts ./scripts
COPY app ./app
RUN pip install --no-cache-dir -e ".[api]"

# The built SPA from stage 1. app.main mounts /app/frontend/dist at / (guarded on its presence).
COPY --from=frontend /frontend/dist ./frontend/dist

# Run as a non-root user (defense-in-depth, even behind nginx). /app is chowned so the editable
# install resolves and the graphs dir (created at runtime by the frozen cluster_graph tool) is
# writable.
RUN useradd --create-home --uid 10001 app && chown -R app:app /app
USER app

# Bind 0.0.0.0 INSIDE the container; docker-compose publishes only to the host's 127.0.0.1,
# where nginx terminates TLS and proxies (the loopback boundary moves to host publishing).
# GRAPHS_DIR stays writable under /app so the frozen agent's cluster_graph writes never error.
ENV ANAMNESIS_GRAPHS_DIR=/app/graphs

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
