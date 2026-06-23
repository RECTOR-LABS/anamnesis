"""Storage abstraction for bi-temporal edges.

`Repository` is the interface both the in-memory test fake and the MongoDB/ApsaraDB
store implement, so the same bi-temporal recall semantics are tested once and
trusted everywhere.
"""
from __future__ import annotations

from typing import Protocol

from .models import Edge, normalize_as_of


class Repository(Protocol):
    def upsert_edge(self, edge: Edge) -> None: ...

    def find_edges(self, entity_key: str, as_of: str | None = None) -> list[Edge]: ...


class InMemoryRepository:
    """Test fake. `find_edges` mirrors the transaction-time semantics of the
    MongoDB store: current view hides superseded edges; an `as_of` view returns
    what was believed at that transaction time."""

    def __init__(self) -> None:
        self._by_id: dict[str, Edge] = {}

    def upsert_edge(self, edge: Edge) -> None:
        self._by_id[edge.id] = edge

    def find_edges(self, entity_key: str, as_of: str | None = None) -> list[Edge]:
        if as_of is not None:
            as_of = normalize_as_of(as_of)  # bare date -> end-of-day UTC; sortable compare
        out: list[Edge] = []
        for e in self._by_id.values():
            if entity_key not in (e.src, e.dst):
                continue
            if as_of is None:
                if e.superseded_at is not None:
                    continue
            else:
                if e.recorded_at > as_of:
                    continue
                if e.superseded_at is not None and e.superseded_at <= as_of:
                    continue
            out.append(e)
        # Stable (recorded_at, id) order so the fake mirrors the Mongo store's
        # sort exactly — both backends agree on sequence, not just membership.
        return sorted(out, key=lambda e: (e.recorded_at, e.id))
