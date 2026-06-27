"""The 'acts' layer — watchlist + alert drafting triggered off a verdict.

Pure over injected memory + alert stores (CI-testable without qwen-agent). The
pure verdict pipeline (assess.py) is unchanged; this module performs the writes.
"""
from __future__ import annotations

from ..memory.graph import ForensicMemory
from ..memory.models import Edge, Provenance, make_edge


def watchlist_add(
    memory: ForensicMemory, deployer: str, mint: str, score: float, now: str
) -> Edge:
    """Record the deployer on the watchlist (a WATCHLISTED edge, deployer -> triggering mint).

    Provenance is `derived` (this is inferred from the verdict, not a first-party on-chain
    observation) — and WATCHLISTED is not a scored type, so a watchlist entry is recall-able
    but can never inflate a future verdict (no feedback loop).
    """
    edge = make_edge(
        "WATCHLISTED", deployer, mint,
        valid_from=now, recorded_at=now,
        provenance=Provenance(
            source="assess_risk", method="derived", confidence=min(1.0, max(0.0, score))
        ),
    )
    memory.remember([edge], now=now)
    return edge
