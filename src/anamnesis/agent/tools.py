"""Anamnesis agent native tools (A.7) over the pure forensic core.

Exposes three capabilities to the Qwen-Agent runtime — ``recall``, ``remember``,
``assess_risk`` — each a thin ``@register_tool`` wrapper around a pure, dependency-
injected handler. The handlers carry the poisoning-defense WRITE-PATH DISCIPLINE and are
unit-tested without the LLM or qwen-agent; the wrappers only adapt JSON args and inject
the deployed singletons. qwen-agent is imported lazily, so this module and its pure
handlers import cleanly in environments that have not installed it.
"""
from __future__ import annotations

import json
from collections.abc import Callable

from ..assess import assess_risk
from ..forensic.helius import build_token_profile
from ..forensic.lp import LpAnalyzer
from ..forensic.pools import DexScreenerClient
from ..forensic.signals import TokenProfile
from ..memory.graph import ForensicMemory
from ..memory.models import Edge, Provenance, make_edge
from ..risk import Verdict

# Provenance source recorded for a model-supplied claim that names none.
CLAIMED_SOURCE = "agent:claimed"


def _clamp01(x: object) -> float:
    try:
        return min(1.0, max(0.0, float(x)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _edge_to_dict(e: Edge) -> dict:
    return {
        "type": e.type,
        "src": e.src,
        "dst": e.dst,
        "method": e.provenance.method,
        "source": e.provenance.source,
        "confidence": e.provenance.confidence,
        "recorded_at": e.recorded_at,
        "valid_from": e.valid_from,
        "valid_to": e.valid_to,
        "superseded_at": e.superseded_at,
    }


def _verdict_to_dict(v: Verdict) -> dict:
    return {
        "level": v.level,
        "score": round(v.score, 4),
        "rationale": v.rationale,
        "signals": [
            {"code": s.code, "severity": s.severity, "detail": s.detail} for s in v.cited_signals
        ],
        "remembered": [_edge_to_dict(e) for e in v.remembered],
    }


def recall_handler(memory: ForensicMemory, entity_key: str, as_of: str | None = None) -> dict:
    """Return everything remembered about a wallet/token (current view, or as-of a past
    transaction time) as a JSON-able dict — the agent's "what do I already know" step."""
    edges = memory.recall(entity_key, as_of)
    return {"entity": entity_key, "as_of": as_of, "edges": [_edge_to_dict(e) for e in edges]}


def remember_handler(memory: ForensicMemory, facts: list[dict], now: str) -> dict:
    """Record model/external-supplied facts as ``claimed`` breadcrumbs.

    WRITE-PATH DISCIPLINE — the poisoning lever lives here. A fact arriving through this
    tool is a CLAIM the agent did not observe first-hand, so its method is forced to
    ``claimed`` no matter what the caller asserts. A first-party finding is stamped only by
    the agent's own grounded on-chain read, never by a (possibly prompt-injected) model —
    so planted breadcrumbs add context but can never forge a first-party rug or move a
    verdict to HIGH.
    """
    edges = []
    for f in facts:
        missing = [k for k in ("type", "src", "dst") if not f.get(k)]
        if missing:
            raise ValueError(f"remember: fact is missing required field(s) {missing}: {f!r}")
        edges.append(
            make_edge(
                f["type"],
                f["src"],
                f["dst"],
                # The agent stamps both time axes from its own clock; the model controls
                # neither transaction time nor validity time (and cannot crash the batch
                # with a malformed timestamp it has no business supplying).
                valid_from=now,
                recorded_at=now,
                provenance=Provenance(
                    source=str(f.get("source") or CLAIMED_SOURCE),
                    method="claimed",  # forced — never first_party/derived from a tool call
                    confidence=_clamp01(f.get("confidence", 0.5)),
                ),
            )
        )
    memory.remember(edges, now=now)
    return {
        "remembered": len(edges),
        "method": "claimed",
        "note": "tool-supplied facts are stored as claimed (context-only) by design",
    }


def assess_risk_handler(
    memory: ForensicMemory,
    build_profile: Callable[[str], TokenProfile],
    mint: str,
    *,
    as_of: str | None = None,
) -> dict:
    """Build a token's profile (grounded read), fuse it with the deployer's remembered
    history, and return the verdict — a clean-looking token from a remembered serial rugger
    is flagged HIGH on memory alone."""
    profile = build_profile(mint)
    verdict = assess_risk(profile, memory, as_of=as_of)
    return _verdict_to_dict(verdict)


def build_lp_aware_profile(helius, dex, mint: str) -> TokenProfile:
    """Build a token profile with the real on-chain LP analyzer wired in.

    The agent's risk VERDICT (assess_risk) must reflect LP securedness, so the analyzer is
    injected here exactly as the MCP get_token_profile entrypoint does. Without it the verdict
    would always see LP as UNKNOWN and the high LP_NOT_SECURED signal could never fire (design:
    "the real LpAnalyzer is injected by the caller (agent assembly / MCP)").
    """
    return build_token_profile(helius, mint, lp_resolver=LpAnalyzer(dex).assess)


# --- Qwen-Agent adapters (defined only when qwen-agent is installed) ------------------
# The pure handlers above never need qwen-agent; importing it lazily keeps this module
# usable in plain test/CI environments. The wrappers below are exercised at agent
# assembly (A.9), where qwen-agent and the live services are present.
try:
    from qwen_agent.tools.base import BaseTool, register_tool
except ImportError:  # pragma: no cover - qwen-agent optional until the agent is assembled
    register_tool = None

if register_tool is not None:  # pragma: no cover - requires qwen-agent + live services
    from datetime import datetime, timezone

    from .. import config
    from ..forensic.helius import HeliusClient
    from ..memory.mongo_store import MongoRepository

    _memory_singleton: ForensicMemory | None = None
    _helius_singleton: HeliusClient | None = None
    _dex_singleton: DexScreenerClient | None = None

    def _memory() -> ForensicMemory:
        global _memory_singleton
        if _memory_singleton is None:
            from pymongo import MongoClient

            client = MongoClient(config.require("ANAMNESIS_MONGODB_URI"))
            _memory_singleton = ForensicMemory(MongoRepository(client, config.ANAMNESIS_DB))
        return _memory_singleton

    def _helius() -> HeliusClient:
        global _helius_singleton
        if _helius_singleton is None:
            _helius_singleton = HeliusClient(config.require("ANAMNESIS_HELIUS_API_KEY"))
        return _helius_singleton

    def _dex() -> DexScreenerClient:
        global _dex_singleton
        if _dex_singleton is None:
            _dex_singleton = DexScreenerClient()
        return _dex_singleton

    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _args(params: object) -> dict:
        return params if isinstance(params, dict) else json.loads(params)

    @register_tool("recall")
    class RecallTool(BaseTool):
        description = (
            "Recall the agent's compounding, provenance-tracked memory about a wallet or "
            "token (and what it knows about that token's deployer). ALWAYS call this before "
            "judging a token."
        )
        parameters = [
            {"name": "entity_key", "type": "string", "required": True,
             "description": "Wallet or mint address to recall history for."},
            {"name": "as_of", "type": "string", "required": False,
             "description": "Optional ISO timestamp for an as-of (time-travel) view."},
        ]

        def call(self, params, **kwargs) -> str:
            a = _args(params)
            return json.dumps(recall_handler(_memory(), a["entity_key"], a.get("as_of")))

    @register_tool("remember")
    class RememberTool(BaseTool):
        description = (
            "Record claimed breadcrumbs (tips, associations, suspicions) about wallets or "
            "tokens. Stored as low-trust 'claimed' provenance (context only) — these cannot "
            "by themselves raise a risk verdict."
        )
        parameters = [
            {"name": "facts", "type": "array", "required": True,
             "description": "List of {type, src, dst, [source], [confidence]} relationship facts."},
        ]

        def call(self, params, **kwargs) -> str:
            a = _args(params)
            return json.dumps(remember_handler(_memory(), a["facts"], _now()))

    @register_tool("assess_risk")
    class AssessRiskTool(BaseTool):
        description = (
            "Assess a token's rug risk by fusing live on-chain signals with the deployer's "
            "REMEMBERED prior-rug history. A clean-looking token from a known serial rugger "
            "is flagged HIGH from memory alone."
        )
        parameters = [
            {"name": "mint", "type": "string", "required": True,
             "description": "The token mint address to assess."},
            {"name": "as_of", "type": "string", "required": False,
             "description": "Optional ISO timestamp for an as-of (time-travel) view."},
        ]

        def call(self, params, **kwargs) -> str:
            a = _args(params)
            return json.dumps(
                assess_risk_handler(
                    _memory(),
                    lambda m: build_lp_aware_profile(_helius(), _dex(), m),
                    a["mint"],
                    as_of=a.get("as_of"),
                )
            )
