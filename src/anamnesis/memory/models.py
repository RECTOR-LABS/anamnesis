"""Bi-temporal forensic graph primitives.

An `Edge` carries two independent time axes plus provenance:
  - valid_from / valid_to       : when the fact was true ON-CHAIN (valid time)
  - recorded_at / superseded_at : when the agent learned/revised it (transaction time)
  - provenance                  : source + method + confidence (for poisoning defense)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone


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


def normalize_as_of(ts: str) -> str:
    """Canonicalize an as-of query bound to a fixed-width ISO-8601 UTC instant so the
    lexicographic comparison in ``find_edges`` is exact across mixed input granularity.

    A bare date means "through the END of that day" (``23:59:59.999999``): a fact
    recorded at any time on that day belongs in the as-of view, and a belief superseded
    earlier that day is correctly excluded. A naive compare drops/keeps such facts
    because a bare date is a lexical PREFIX of a same-day datetime and so sorts before
    it. A value that already carries a time is converted to UTC as-is; fixed-width
    microseconds keep every emitted string mutually sortable.
    """
    if "T" in ts:
        dt = datetime.fromisoformat(ts)
        dt = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    else:
        dt = datetime.combine(date.fromisoformat(ts), time(23, 59, 59, 999999), tzinfo=timezone.utc)
    return dt.isoformat(timespec="microseconds")
