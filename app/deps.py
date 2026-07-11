"""Process-lifetime singletons over the frozen engine, plus the API's single assess(mint) entry.

Wraps the exact constructors `anamnesis.agent.tools` uses for its qwen-agent tool singletons
(ForensicMemory over MongoRepository, the Mongo-backed AlertStore, HeliusClient,
DexScreenerClient) as `functools.lru_cache(maxsize=1)` module-level accessors, available
whether or not qwen-agent is installed. tools.py's originals live inside an
`if register_tool is not None:` block gated on qwen-agent's presence (it only needs them when
assembling the Qwen-Agent Assistant); the FastAPI process needs the same singletons
unconditionally, so this module builds its own. `build_profile` (the LP-aware profile builder)
is wired the same way but deliberately NOT cached — see its docstring — a live rug detector
must never keep serving a "clean" verdict for a mint that rugged since the last time it was
read. Engine is FROZEN: nothing here reimplements assess_risk/assess_and_act, it only wires the
existing constructors together for the routes.

CI-safety: every top-level import below is qwen-agent-free (pymongo, anamnesis.forensic.*,
anamnesis.memory.*, anamnesis.agent.tools, anamnesis.agent.actions — none pull in qwen-agent at
import time). Only get_agent() touches qwen-agent, via a lazy import inside the function body,
so `import app.deps` succeeds in CI (which installs no qwen-agent/mcp/openai).
"""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
import os

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
    """One Mongo client shared by memory + alerts (mirrors agent.tools._client).

    The frozen engine reads `ANAMNESIS_MONGODB_URI`; the Vercel MongoDB Atlas marketplace
    integration auto-injects the connection string as `MONGODB_URI` (sensitive — not
    readable via `vercel env pull`). Bridge them here: prefer the engine's name, fall back
    to the integration's. This is deploy-serialization glue (api/app layer), not engine.
    """
    from pymongo import MongoClient

    uri = os.environ.get("ANAMNESIS_MONGODB_URI") or os.environ.get("MONGODB_URI")
    if not uri:
        raise RuntimeError(
            "ANAMNESIS_MONGODB_URI is not set. Copy .env.example to .env and fill in "
            "ANAMNESIS_MONGODB_URI, or connect the Vercel MongoDB Atlas integration (which "
            "injects MONGODB_URI)."
        )
    return MongoClient(uri)


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


def build_profile(mint: str) -> TokenProfile:
    """The exact LP-aware profile builder the agent uses (anamnesis.agent.tools). Deliberately
    UNCACHED (no lru_cache): a live rug detector must never keep answering "clean" for a mint
    that rugged minutes ago just because an earlier request's read got cached. assess() below
    still avoids a second Helius/DexScreener round-trip per request — via a closure, not a
    cache; see its docstring."""
    return build_lp_aware_profile(get_helius(), get_dex(), mint)


def assess(mint: str) -> dict:
    """Run the engine's full assess_and_act pipeline for `mint` and shape the dict the API
    routes need.

    Returns the engine's raw result dict verbatim (`level` stays lowercase
    "high"/"medium"/"low" — `verdict_card` is the boundary that uppercases it for the
    dashboard, not this function) plus `mint` (echoed back; assess_and_act never puts it on
    the result) and `deployer` (read off the profile). `build_profile(mint)` is called exactly
    ONCE here — referenced as the bare module global (not a locally bound alias) so tests can
    still monkeypatch `deps.build_profile` — and the resulting profile is threaded into
    assess_and_act via a `lambda _m: profile` closure, so assess_and_act's own internal call
    reuses that same fresh profile instead of triggering a second Helius/DexScreener round-trip.
    """
    profile = build_profile(mint)
    result = assess_and_act(get_memory(), get_alerts(), lambda _m: profile, mint, _now())
    result["mint"] = mint
    result["deployer"] = profile.deployer
    return result


@lru_cache(maxsize=1)
def get_agent():
    """Lazy qwen-agent Assistant singleton. Imports anamnesis.agent.agent (which pulls in
    qwen-agent) inside the function body — not at module top — so `import app.deps` stays
    CI-safe. Exercised by Task 4's chat SSE route, not unit-tested here (CI has no qwen-agent
    installed)."""
    from anamnesis.agent.agent import build_agent

    return build_agent()
