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


def _canonical(ts: str, *, day_time: time) -> str:
    """Parse a bare date or ISO datetime and emit a fixed-width ISO-8601 UTC instant.

    A bare date is combined with ``day_time``; a value already carrying a time is
    converted to UTC (a naive one is assumed UTC). Fixed-width microseconds make every
    emitted string mutually sortable, so the lexicographic comparison in ``find_edges``
    is exact regardless of the caller's input granularity or offset.
    """
    if "T" in ts:
        dt = datetime.fromisoformat(ts)
        dt = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    else:
        dt = datetime.combine(date.fromisoformat(ts), day_time, tzinfo=timezone.utc)
    return dt.isoformat(timespec="microseconds")


def normalize_instant(ts: str) -> str:
    """Canonicalize an EVENT timestamp (recorded_at / valid_* / superseded_at / the
    supersession ``now``). A bare date is the START of that day (00:00:00) — the moment
    the day's record begins."""
    return _canonical(ts, day_time=time(0, 0, 0))


def normalize_as_of(ts: str) -> str:
    """Canonicalize an as-of query bound. A bare date means "through the END of that day"
    (23:59:59.999999): a fact recorded at any time on that day belongs in the as-of view,
    and a belief superseded earlier that day is correctly excluded — otherwise a bare date
    (a lexical PREFIX of a same-day datetime) sorts before it and drops/keeps facts
    wrongly."""
    return _canonical(ts, day_time=time(23, 59, 59, 999999))


def make_edge(
    type: str,
    src: str,
    dst: str,
    *,
    valid_from: str,
    recorded_at: str,
    provenance: Provenance,
    valid_to: str | None = None,
    superseded_at: str | None = None,
) -> Edge:
    """The canonical write-path constructor: build an Edge with every temporal field
    canonicalized to a fixed-width ISO-8601 UTC instant and a provenance-complete id
    derived from the NORMALIZED recorded_at. All writers (agent tools, demo seed, tests of
    write behaviour) go through it, so the stored-timestamp invariant the as-of recall
    relies on holds by construction rather than by each caller's discipline — closing the
    leak where a `Z`- or offset-suffixed stored timestamp would defeat the read-side
    normalization in ``find_edges``.
    """
    rec = normalize_instant(recorded_at)
    return Edge(
        id=make_edge_id(type, src, dst, rec, provenance.method, provenance.source),
        type=type,
        src=src,
        dst=dst,
        valid_from=normalize_instant(valid_from),
        valid_to=normalize_instant(valid_to) if valid_to is not None else None,
        recorded_at=rec,
        superseded_at=normalize_instant(superseded_at) if superseded_at is not None else None,
        provenance=provenance,
    )
