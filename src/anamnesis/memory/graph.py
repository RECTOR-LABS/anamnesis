"""ForensicMemory — the compounding, bi-temporal memory over a `Repository`.

`remember` writes findings (superseding prior beliefs in transaction time);
`recall` / `recall_deployer_history` read them back (current or as-of a past
transaction time); `trust_weighted_risk` aggregates remembered risk into a score.

This is the poisoning defense, and it rests on one observation: of an edge's
provenance, only `method` is unforgeable. The agent stamps `first_party` solely
on its OWN grounded on-chain read — an attacker who poisons memory can forge the
`source` string and the `confidence` float and plant unlimited `claimed`
breadcrumbs, but cannot make a fake rug appear in the agent's own Helius
observation. So risk is driven by distinct FIRST-PARTY rugged tokens, the
forgeable `source` is never counted, and `claimed`/`derived` evidence can never
reach HIGH at any volume.
"""
from __future__ import annotations

from .models import Edge
from .repository import Repository

# How much each remembered relationship contributes to risk before trust-weighting.
# RUGGED = direct prior-rug evidence; SAME_CLUSTER = guilt-by-association (discounted).
RISK_WEIGHTS = {"RUGGED": 1.0, "SAME_CLUSTER": 0.5}

# How far to trust an edge by HOW it was learned — the poisoning lever. A first-party
# on-chain observation is fully trusted; a derived inference less so; a `claimed`
# breadcrumb (which an adversary can plant) carries near-zero weight.
METHOD_TRUST = {"first_party": 1.0, "derived": 0.6, "claimed": 0.1}

# Band ceiling per method: the score may not exceed the ceiling of the strongest
# contributing method. Only a first-party observation can reach HIGH; a `derived`
# inference is capped at MEDIUM. `claimed` is intentionally ABSENT — it scores zero
# magnitude (context-only), so no number of planted breadcrumbs can raise the score.
METHOD_CEILING = {"first_party": 1.0, "derived": 0.5}

# Methods that contribute risk magnitude (those with a ceiling). `claimed` is excluded:
# it is stored and recalled, but cannot move the verdict.
SCORING_METHODS = frozenset(METHOD_CEILING)

# Per-distinct-fact risk, combined by noisy-OR across distinct rugged tokens. Tuned so
# one first-party rug lands MEDIUM and a second distinct one tips HIGH — the
# "serial rugger flagged on sight" boundary.
PER_FACT_SCALE = 0.47


def _validate_method(method: str) -> None:
    """Fail closed on an unknown/typo'd method rather than silently scoring it low."""
    if method not in METHOD_TRUST:
        raise ValueError(
            f"unknown provenance.method {method!r}; expected one of {sorted(METHOD_TRUST)}"
        )


def _edge_trust(edge: Edge) -> float:
    """How much an edge should count — method-trust scaled by stated confidence."""
    _validate_method(edge.provenance.method)
    return METHOD_TRUST[edge.provenance.method] * edge.provenance.confidence


def _supersedes(new: Edge, prior: Edge) -> bool:
    """Whether `new` should retire `prior` belief about the same (src, type, dst).

    A new belief supersedes a prior one only if it is strictly better-supported, or
    if it is the SAME source revising itself at equal trust. Independent sources at
    equal trust coexist as corroboration (not collapsed), and a lower-trust edge —
    e.g. a planted `claimed` re-assertion — can never bury a higher-trust first-party
    belief.
    """
    nt, pt = _edge_trust(new), _edge_trust(prior)
    return nt > pt or (nt == pt and new.provenance.source == prior.provenance.source)


class ForensicMemory:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def remember(self, edges: list[Edge], now: str) -> None:
        for edge in edges:  # fail closed before any write — no partial supersession
            _validate_method(edge.provenance.method)
        for edge in edges:
            for prior in self.repo.find_edges(edge.src):
                if prior.id != edge.id and prior.superseded_at is None \
                        and (prior.src, prior.type, prior.dst) == (edge.src, edge.type, edge.dst) \
                        and _supersedes(edge, prior):
                    prior.superseded_at = now
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
        for e in edges:  # fail closed on any malformed edge before scoring
            _validate_method(e.provenance.method)
        # One fact per (type, dst), keeping only the highest-trust edge. Forgeable
        # `source` strings are never counted, so neither sybil sources nor same-fact
        # spam can manufacture corroboration — only distinct rugged tokens raise risk.
        best: dict[tuple[str, str], Edge] = {}
        for e in edges:
            if e.type not in RISK_WEIGHTS:
                continue
            k = (e.type, e.dst)
            if k not in best or _edge_trust(e) > _edge_trust(best[k]):
                best[k] = e
        # Magnitude: noisy-OR over distinct AUTHENTICATED facts (first_party/derived).
        # `claimed` is context-only (skipped). The result is capped by the strongest
        # method present, so claimed/derived can never reach HIGH at any scale.
        product = 1.0
        ceiling = 0.0
        for (etype, _dst), e in best.items():
            method = e.provenance.method
            if method not in SCORING_METHODS:
                continue
            p = min(RISK_WEIGHTS[etype] * _edge_trust(e) * PER_FACT_SCALE, 1.0)
            product *= 1.0 - p
            ceiling = max(ceiling, METHOD_CEILING[method])
        return min(1.0 - product, ceiling)
