"""MongoRepository unit tests — the Mongo-specific behaviours the cross-backend
contract (test_memory_models / test_memory_graph under --store=mongo) does not
assert: full document fidelity, upsert idempotency, and index creation. These run
on every `pytest` invocation against mongomock, so the Mongo translation is covered
even without a live server.
"""
import pytest

from anamnesis.memory.models import Edge, Provenance, make_edge_id
from anamnesis.memory.mongo_store import MongoRepository

# mongomock stands in for a server; skip (don't error) the whole module if a minimal
# environment hasn't installed it, so a plain `pytest` without it degrades gracefully.
mongomock = pytest.importorskip("mongomock")

DB = "anamnesis_test"


def _edge(**kw) -> Edge:
    base = dict(
        type="RUGGED", src="wallet1", dst="mintA",
        valid_from="2026-01-01", valid_to=None, recorded_at="2026-06-01",
        superseded_at=None, provenance=Provenance("helius:getAsset", "first_party", 0.95),
    )
    base.update(kw)
    base["id"] = make_edge_id(base["type"], base["src"], base["dst"], base["recorded_at"])
    return Edge(**base)


@pytest.fixture
def mongo_repo() -> MongoRepository:
    return MongoRepository(mongomock.MongoClient(), DB)


def test_roundtrip_preserves_every_field(mongo_repo):
    edge = _edge()
    mongo_repo.upsert_edge(edge)
    [back] = mongo_repo.find_edges("wallet1")
    assert back == edge  # full Edge + nested Provenance fidelity through the document


def test_reupsert_same_id_keeps_a_single_edge(mongo_repo):
    # Re-investigating the same fact must revise in place, never duplicate —
    # the compounding-memory invariant.
    mongo_repo.upsert_edge(_edge(superseded_at=None))
    mongo_repo.upsert_edge(_edge(superseded_at="2026-06-09"))  # same id, revised belief
    edges = mongo_repo.find_edges("wallet1", as_of="2026-06-05")
    assert len(edges) == 1
    assert edges[0].superseded_at == "2026-06-09"


def test_constructor_creates_unique_id_and_endpoint_indexes(mongo_repo):
    info = mongo_repo._col.index_information()
    keyed = {tuple(field for field, _ in v["key"]): v for v in info.values()}
    assert ("id",) in keyed and ("src",) in keyed and ("dst",) in keyed
    assert keyed[("id",)].get("unique") is True
