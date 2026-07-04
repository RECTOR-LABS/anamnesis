"""Process-lifetime singletons over the frozen engine, plus the API's single assess(mint) entry.

Wraps the exact constructors `anamnesis.agent.tools` uses for its qwen-agent tool singletons
(ForensicMemory over MongoRepository, the Mongo-backed AlertStore, HeliusClient,
DexScreenerClient, and the LP-aware profile builder) as `functools.lru_cache(maxsize=1)`
module-level accessors, available whether or not qwen-agent is installed. tools.py's originals
live inside an `if register_tool is not None:` block gated on qwen-agent's presence (it only
needs them when assembling the Qwen-Agent Assistant); the FastAPI process needs the same
singletons unconditionally, so this module builds its own. Engine is FROZEN: nothing here
reimplements assess_risk/assess_and_act, it only wires the existing constructors together for
the routes.

CI-safety: every top-level import below is qwen-agent-free (pymongo, anamnesis.forensic.*,
anamnesis.memory.*, anamnesis.agent.tools, anamnesis.agent.actions — none pull in qwen-agent at
import time). Only get_agent() touches qwen-agent, via a lazy import inside the function body,
so `import api.deps` succeeds in CI (which installs no qwen-agent/mcp/openai).
"""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache

from anamnesis import config
from anamnesis.agent.actions import assess_and_act
from anamnesis.agent.tools import build_lp_aware_profile
from anamnesis.forensic.helius import HeliusClient
from anamnesis.forensic.pools import DexScreenerClient
from anamnesis.forensic.signals import TokenProfile
from anamnesis.memory.alerts import AlertStore, MongoAlertStore
from anamnesis.memory.graph import ForensicMemory
from anamnesis.memory.mongo_store import MongoRepository


@lru_cache(maxsize=1)
def _client():
    """One Mongo client shared by memory + alerts (mirrors agent.tools._client)."""
    from pymongo import MongoClient

    return MongoClient(config.require("ANAMNESIS_MONGODB_URI"))


@lru_cache(maxsize=1)
def get_memory() -> ForensicMemory:
    return ForensicMemory(MongoRepository(_client(), config.ANAMNESIS_DB))


@lru_cache(maxsize=1)
def get_alerts() -> AlertStore:
    return MongoAlertStore(_client(), config.ANAMNESIS_DB)


@lru_cache(maxsize=1)
def get_helius() -> HeliusClient:
    return HeliusClient(config.require("ANAMNESIS_HELIUS_API_KEY"))


@lru_cache(maxsize=1)
def get_dex() -> DexScreenerClient:
    return DexScreenerClient()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@lru_cache(maxsize=256)
def build_profile(mint: str) -> TokenProfile:
    """The exact LP-aware profile builder the agent uses (anamnesis.agent.tools), cached per
    mint so assess()'s second read below (for `deployer`) is a cache hit, not a second
    Helius/DexScreener round-trip."""
    return build_lp_aware_profile(get_helius(), get_dex(), mint)


def assess(mint: str) -> dict:
    """Run the engine's full assess_and_act pipeline for `mint` and shape the dict the API
    routes need.

    Returns the engine's raw result dict verbatim (`level` stays lowercase
    "high"/"medium"/"low" — `verdict_card` is the boundary that uppercases it for the
    dashboard, not this function) plus `mint` (echoed back; assess_and_act never puts it on
    the result) and `deployer` (read off the profile). `build_profile` is referenced here as
    the bare module global — not a locally bound alias — both so tests can monkeypatch
    `deps.build_profile` and so this second call and assess_and_act's internal one share one
    lru_cache entry per mint.
    """
    result = assess_and_act(get_memory(), get_alerts(), build_profile, mint, _now())
    result["mint"] = mint
    result["deployer"] = build_profile(mint).deployer
    return result


@lru_cache(maxsize=1)
def get_agent():
    """Lazy qwen-agent Assistant singleton. Imports anamnesis.agent.agent (which pulls in
    qwen-agent) inside the function body — not at module top — so `import api.deps` stays
    CI-safe. Exercised by Task 4's chat SSE route, not unit-tested here (CI has no qwen-agent
    installed)."""
    from anamnesis.agent.agent import build_agent

    return build_agent()
