# Anamnesis runtime: the Qwen-Agent WebUI (app.py) which spawns the forensic MCP server as a
# stdio child and runs the cluster-graph static server in a daemon thread.
FROM python:3.12-slim

# soundfile (imported transitively by qwen_agent) needs libsndfile at runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# EDITABLE install is required, not optional: agent.py resolves mcp/solana_forensics_mcp.py
# relative to its own location (repo root), so the source must stay laid out as src/ + mcp/.
COPY pyproject.toml ./
COPY src ./src
COPY mcp ./mcp
COPY scripts ./scripts
COPY app.py ./
RUN pip install --no-cache-dir -e .

# Run as a non-root user (defense-in-depth, even behind nginx). /app is chowned so the editable
# install resolves and the graphs dir (created at runtime via os.makedirs) is writable.
RUN useradd --create-home --uid 10001 app && chown -R app:app /app
USER app

# Bind 0.0.0.0 INSIDE the container; docker-compose publishes only to the host's 127.0.0.1,
# where nginx terminates TLS and proxies (the loopback boundary moves to host publishing).
ENV ANAMNESIS_WEBUI_HOST=0.0.0.0 \
    ANAMNESIS_WEBUI_PORT=7860 \
    ANAMNESIS_GRAPHS_HOST=0.0.0.0 \
    ANAMNESIS_GRAPHS_PORT=7866 \
    ANAMNESIS_GRAPHS_DIR=/app/graphs

EXPOSE 7860 7866
CMD ["python", "app.py"]
