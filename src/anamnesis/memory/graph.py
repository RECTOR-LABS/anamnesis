"""ForensicMemory — the compounding, bi-temporal memory over a `Repository`.

`remember` writes findings (superseding prior beliefs in transaction time);
`recall` / `recall_deployer_history` read them back (current or as-of a past
transaction time); `trust_weighted_risk` aggregates remembered risk into a score.

This is the poisoning defense, and it rests on one observation: of an edge's
provenance, only `method` is unforgeable. The agent stamps `first_party` solely
on its OWN grounded on-chain read — an attacker who poisons memory can forge the
`source` string and the `confidence` float and plant unlimited `claimed`
breadcrumbs, but cannot make a fake rug appear in the agent's own Helius
observation. So method RANK (not the forgeable source or confidence) drives both
supersession and scoring: risk comes from distinct FIRST-PARTY rugged tokens, the
forgeable `source` is never counted, `claimed`/`derived` evidence can never reach
HIGH at any volume — even mixed with a genuine first-party rug — and guilt-by-
association (`SAME_CLUSTER`) is capped at MEDIUM however many links accrue.
"""
from __future__ import annotations

from .models import Edge, normalize_instant
from .repository import Repository

# How much each remembered relationship contributes to risk before trust-weighting.
# RUGGED = direct prior-rug evidence; SAME_CLUSTER = guilt-by-association (discounted).
RISK_WEIGHTS = {"RUGGED": 1.0, "SAME_CLUSTER": 0.5}

# Band ceiling per relationship TYPE, independent of method. Direct RUGGED evidence may
# reach HIGH; SAME_CLUSTER (guilt-by-association) is capped at MEDIUM however many distinct
# first-party links accrue — association corroborates but, alone, never drives the top
# verdict (only an observed rug does). A fact's effective ceiling is min(method, type).
TYPE_CEILING = {"RUGGED": 1.0, "SAME_CLUSTER": 0.5}

# How far to trust an edge by HOW it was learned — the poisoning lever. A first-party
# on-chain observation is fully trusted; a derived inference less so; a `claimed`
# breadcrumb (which an adversary can plant) carries near-zero weight.
METHOD_TRUST = {"first_party": 1.0, "derived": 0.6, "claimed": 0.1}

# Ordinal trust of each method — the UNFORGEABLE axis. Supersession and per-fact
# tiering rank by this FIRST (confidence only ever weighs magnitude WITHIN a method),
# so a higher-confidence lower-method edge can never out-rank or bury a first-party one.
METHOD_RANK = {"first_party": 2, "derived": 1, "claimed": 0}

# Band ceiling per method: a fact's risk may not exceed the ceiling of its method tier.
# Only a first-party observation can reach HIGH; a `derived` inference is capped at
# MEDIUM. `claimed` is intentionally ABSENT — it scores zero magnitude (context-only),
# so no number of planted breadcrumbs can raise the score.
METHOD_CEILING = {"first_party": 1.0, "derived": 0.5}

# Methods that contribute risk magnitude (those with a ceiling). `claimed` is excluded:
# it is stored and recalled, but cannot move the verdict.
SCORING_METHODS = frozenset(METHOD_CEILING)

# The same ceilings keyed by method rank, for the per-tier aggregation in scoring.
RANK_CEILING = {METHOD_RANK[m]: c for m, c in METHOD_CEILING.items()}

# Per-distinct-fact risk, combined by noisy-OR across distinct rugged tokens within a
# tier. Tuned against the risk.py bands (HIGH 0.6 / MEDIUM 0.3) so one first-party rug
# lands MEDIUM and a second distinct one tips HIGH — the "serial rugger on sight" line.
PER_FACT_SCALE = 0.47


def _validate_method(method: str) -> None:
    """Fail closed on an unknown/typo'd method rather than silently scoring it low."""
    if method not in METHOD_TRUST:
        raise ValueError(
            f"unknown provenance.method {method!r}; expected one of {sorted(METHOD_TRUST)}"
        )


def _edge_trust(edge: Edge) -> float:
    """How much an edge should count — method-trust scaled by confidence (clamped to
    [0,1] so a forged out-of-range confidence cannot invert or saturate the score)."""
    _validate_method(edge.provenance.method)
    confidence = min(1.0, max(0.0, edge.provenance.confidence))
    return METHOD_TRUST[edge.provenance.method] * confidence


def _supersedes(new: Edge, prior: Edge) -> bool:
    """Whether `new` should retire `prior` belief about the same (src, type, dst).

    Method rank dominates: a weaker-method edge (e.g. a planted `claimed`
    re-assertion) can NEVER retire a stronger-method belief, whatever its confidence
    or source. Within an equal-or-higher method, a new belief supersedes only if it
    is strictly better-supported, or is the SAME source revising itself at equal
    trust; independent sources at equal trust coexist as corroboration.
    """
    _validate_method(new.provenance.method)
    _validate_method(prior.provenance.method)  # `prior` came from the store — fail closed
    if METHOD_RANK[new.provenance.method] < METHOD_RANK[prior.provenance.method]:
        return False
    nt, pt = _edge_trust(new), _edge_trust(prior)
    return nt > pt or (nt == pt and new.provenance.source == prior.provenance.source)


class ForensicMemory:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def remember(self, edges: list[Edge], now: str) -> None:
        for edge in edges:  # fail closed before any write — no partial supersession
            _validate_method(edge.provenance.method)
        now = normalize_instant(now)  # stamp supersession in the canonical instant space
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
        # Best scoring-trust per (type, dst, method-rank). A fact contributes to EVERY
        # method tier it has evidence in, so a high-confidence `derived` edge counts in
        # the derived tier (capped at MEDIUM) even when the token also carries a
        # first-party observation — derived can corroborate up to MEDIUM but never lend
        # its magnitude to the first-party (HIGH-capable) tier. Forgeable `source` is
        # never counted; `claimed` is context-only (skipped here).
        fact_trust: dict[tuple[str, str, int], float] = {}
        for e in edges:
            if e.type not in RISK_WEIGHTS or e.provenance.method not in SCORING_METHODS:
                continue
            k = (e.type, e.dst, METHOD_RANK[e.provenance.method])
            fact_trust[k] = max(fact_trust.get(k, 0.0), _edge_trust(e))
        # Noisy-OR over distinct facts WITHIN each (method-rank, type) tier (sorted keys →
        # bit-stable float order), capped at that tier's EFFECTIVE ceiling — the lesser of
        # the method ceiling (derived caps at MEDIUM) and the type ceiling (SAME_CLUSTER
        # caps at MEDIUM). The verdict is the strongest tier, so HIGH is reachable only via
        # directly-observed first-party RUGS; derived inference and cluster association each
        # corroborate up to MEDIUM but can never, at any scale, drive the top verdict.
        tier_product: dict[tuple[int, str], float] = {}
        for (etype, _dst, rank) in sorted(fact_trust):
            p = min(RISK_WEIGHTS[etype] * fact_trust[(etype, _dst, rank)] * PER_FACT_SCALE, 1.0)
            tier_product[(rank, etype)] = tier_product.get((rank, etype), 1.0) * (1.0 - p)
        return max(
            (
                min(1.0 - prod, RANK_CEILING[rank], TYPE_CEILING[etype])
                for (rank, etype), prod in tier_product.items()
            ),
            default=0.0,
        )
