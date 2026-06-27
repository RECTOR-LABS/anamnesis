"""Central environment + endpoint configuration.

One place to resolve secrets and service endpoints, with actionable errors so a
missing value fails loudly and says exactly how to fix it. Secrets are read from
the environment only (never argv, never committed): copy .env.example to .env and
fill it in.
"""

from __future__ import annotations

import os

# Qwen via DashScope — the international, OpenAI-compatible endpoint (hard rule).
DASHSCOPE_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

# Model id can drift or vary by region; override via QWEN_MODEL in .env if the
# default is rejected on the international endpoint (documented fallback: qwen-plus).
QWEN_MODEL = os.environ.get("QWEN_MODEL", "qwen-max")

# Memory database name (ApsaraDB for MongoDB, or a local Mongo in tests).
ANAMNESIS_DB = os.environ.get("ANAMNESIS_DB", "anamnesis")


def require(name: str) -> str:
    """Return env var ``name``; raise an actionable error if it is unset or empty."""
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(
            f"{name} is not set. Copy .env.example to .env and fill in {name}."
        )
    return val


def helius_rpc_url() -> str:
    """Helius Solana mainnet RPC URL, keyed from the environment.

    The API key travels in the query string per Helius's design; it is read from
    ANAMNESIS_HELIUS_API_KEY and must never be logged.
    """
    return f"https://mainnet.helius-rpc.com/?api-key={require('ANAMNESIS_HELIUS_API_KEY')}"


# Relationship-graph view (B.2). Where rendered cluster HTML is written, and the base URL the
# agent links to (a minimal static server over GRAPHS_DIR is launched by app.py).
GRAPHS_DIR = os.environ.get("ANAMNESIS_GRAPHS_DIR", "graphs")
GRAPHS_PORT = int(os.environ.get("ANAMNESIS_GRAPHS_PORT", "7866"))
GRAPHS_BASE_URL = os.environ.get("ANAMNESIS_GRAPHS_BASE_URL", f"http://localhost:{GRAPHS_PORT}")

# Bind hosts for the WebUI (Gradio) and the graph static server. Default to loopback (the
# served-port infra rule); a container sets these to 0.0.0.0 so Docker can publish the ports to
# the host's 127.0.0.1, where nginx proxies them — the loopback boundary moves to host publishing.
WEBUI_HOST = os.environ.get("ANAMNESIS_WEBUI_HOST", "127.0.0.1")
WEBUI_PORT = int(os.environ.get("ANAMNESIS_WEBUI_PORT", "7860"))
GRAPHS_HOST = os.environ.get("ANAMNESIS_GRAPHS_HOST", "127.0.0.1")
