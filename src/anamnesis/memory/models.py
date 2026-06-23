"""Bi-temporal forensic graph primitives.

An `Edge` carries two independent time axes plus provenance:
  - valid_from / valid_to       : when the fact was true ON-CHAIN (valid time)
  - recorded_at / superseded_at : when the agent learned/revised it (transaction time)
  - provenance                  : source + method + confidence (for poisoning defense)
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Provenance:
    source: str  # e.g. "helius:getAsset"
    method: str  # "first_party" | "derived" | "claimed"
    confidence: float  # 0..1


@dataclass
class Edge:
    id: str
    type: str  # DEPLOYED | FUNDED_BY | PROVIDES_LP | SAME_CLUSTER | RUGGED
    src: str
    dst: str
    valid_from: str
    valid_to: str | None
    recorded_at: str
    superseded_at: str | None
    provenance: Provenance


def make_edge_id(
    type: str, src: str, dst: str, recorded_at: str, method: str, source: str
) -> str:
    """A deterministic edge identity that INCLUDES provenance (method, source).

    Two beliefs about the same (type, src, dst) recorded the same day but learned a
    different WAY (method) or from a different SOURCE are distinct edges. Folding both
    into the id means a planted `claimed` breadcrumb can neither share an id with nor
    overwrite (last-write-wins) a genuine first-party observation, and independent
    same-day corroboration coexists instead of one silently clobbering the other.
    `method` is a fixed enum with no delimiter, so the `#method:source` segment parses
    unambiguously — though the id is only ever compared for equality, never split.
    """
    return f"{type}:{src}->{dst}@{recorded_at}#{method}:{source}"
