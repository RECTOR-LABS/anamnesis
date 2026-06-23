"""ForensicMemory — the compounding, bi-temporal memory over a `Repository`.

`remember` writes findings (superseding prior beliefs in transaction time);
`recall` / `recall_deployer_history` read them back (current or as-of a past
transaction time); `trust_weighted_risk` aggregates remembered risk so that
provenance and independent-source corroboration — not raw count — drive the
score, which is the poisoning defense: a single low-confidence seeded edge
cannot dominate a corroborated, first-party history.
"""
from __future__ import annotations

from collections import defaultdict

from .models import Edge
from .repository import Repository

# How much each remembered relationship contributes to risk before trust-weighting.
# RUGGED = direct prior-rug evidence; SAME_CLUSTER = guilt-by-association (discounted).
RISK_WEIGHTS = {"RUGGED": 1.0, "SAME_CLUSTER": 0.5}


class ForensicMemory:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def remember(self, edges: list[Edge], now: str) -> None:
        for edge in edges:
            for prior in self.repo.find_edges(edge.src):
                if (prior.type, prior.dst) == (edge.type, edge.dst) \
                        and prior.superseded_at is None and prior.id != edge.id:
                    prior.superseded_at = now  # transaction-time supersession
                    self.repo.upsert_edge(prior)
            self.repo.upsert_edge(edge)

    def recall(self, entity_key: str, as_of: str | None = None) -> list[Edge]:
        return self.repo.find_edges(entity_key, as_of)

    def recall_deployer_history(self, wallet: str, as_of: str | None = None) -> list[Edge]:
        return [
            e for e in self.repo.find_edges(wallet, as_of)
            if e.src == wallet and e.type in ("DEPLOYED", "RUGGED")
        ]

    def trust_weighted_risk(self, edges: list[Edge]) -> float:
        groups: dict[tuple[str, str], list[Edge]] = defaultdict(list)
        for e in edges:
            if e.type in RISK_WEIGHTS:
                groups[(e.type, e.dst)].append(e)
        score = 0.0
        for (etype, _dst), items in groups.items():
            corroboration = min(len({e.provenance.source for e in items}), 3) / 3.0
            best_conf = max(e.provenance.confidence for e in items)
            score += RISK_WEIGHTS[etype] * best_conf * (0.4 + 0.6 * corroboration)
        return min(score, 1.0)
