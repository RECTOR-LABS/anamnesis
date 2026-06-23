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
    HELIUS_API_KEY and must never be logged.
    """
    return f"https://mainnet.helius-rpc.com/?api-key={require('HELIUS_API_KEY')}"
