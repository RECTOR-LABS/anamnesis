"""MongoRepository — the ApsaraDB-for-MongoDB implementation of the `Repository`
protocol (A.2), so the bi-temporal recall semantics proven against the in-memory
fake hold identically against the managed store.

Edges live in the `relations` collection, keyed by their deterministic `id`
(unique-indexed) so re-investigating a fact revises it in place rather than
duplicating. `find_edges` translates the fake's transaction-time filters into a
Mongo query verbatim — the translation is exact because both compare zero-padded
ISO-8601 timestamps lexicographically. That ordering is load-bearing: every
temporal field MUST be a zero-padded ISO-8601 string.
"""
from __future__ import annotations

from typing import Any

from .models import Edge, Provenance, normalize_as_of

COLLECTION = "relations"


def _to_doc(edge: Edge) -> dict[str, Any]:
    """Serialize an `Edge` to its `relations` document (provenance nested)."""
    p = edge.provenance
    return {
        "id": edge.id,
        "type": edge.type,
        "src": edge.src,
        "dst": edge.dst,
        "valid_from": edge.valid_from,
        "valid_to": edge.valid_to,
        "recorded_at": edge.recorded_at,
        "superseded_at": edge.superseded_at,
        "provenance": {"source": p.source, "method": p.method, "confidence": p.confidence},
    }


def _from_doc(doc: dict[str, Any]) -> Edge:
    """Reconstruct an `Edge` from a `relations` document (ignores Mongo's `_id`)."""
    p = doc["provenance"]
    return Edge(
        id=doc["id"],
        type=doc["type"],
        src=doc["src"],
        dst=doc["dst"],
        valid_from=doc["valid_from"],
        valid_to=doc.get("valid_to"),
        recorded_at=doc["recorded_at"],
        superseded_at=doc.get("superseded_at"),
        provenance=Provenance(p["source"], p["method"], p["confidence"]),
    )


class MongoRepository:
    """`Repository` over a MongoDB / ApsaraDB `relations` collection.

    Takes a connected pymongo-compatible ``client`` plus the database name; the
    caller owns the client's lifecycle. Indexes are created on construction.
    """

    def __init__(self, client: Any, db_name: str) -> None:
        self._col = client[db_name][COLLECTION]
        self._col.create_index("id", unique=True)
        self._col.create_index("src")
        self._col.create_index("dst")

    def upsert_edge(self, edge: Edge) -> None:
        self._col.replace_one({"id": edge.id}, _to_doc(edge), upsert=True)

    def find_edges(self, entity_key: str, as_of: str | None = None) -> list[Edge]:
        if as_of is not None:
            as_of = normalize_as_of(as_of)  # bare date -> end-of-day UTC; sortable compare
        clauses: list[dict[str, Any]] = [
            {"$or": [{"src": entity_key}, {"dst": entity_key}]},
        ]
        if as_of is None:
            clauses.append({"superseded_at": None})  # current view hides superseded beliefs
        else:
            clauses.append({"recorded_at": {"$lte": as_of}})  # already known by then
            clauses.append(  # and not yet superseded as of then
                {"$or": [{"superseded_at": None}, {"superseded_at": {"$gt": as_of}}]}
            )
        docs = self._col.find({"$and": clauses}).sort([("recorded_at", 1), ("id", 1)])
        return [_from_doc(d) for d in docs]
