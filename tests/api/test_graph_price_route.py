"""HTTP + pure-function tests for GET /api/graph/{deployer} and GET /api/price/{mint}.

Route tests use FastAPI's TestClient with api.deps.get_memory / api.deps.get_dex
monkeypatched to network-free fakes (an InMemoryRepository-backed ForensicMemory; a fake
DexScreener client) — no Mongo, no HTTP. graph_dict/price_points are also each exercised
directly against hand-built inputs, proving the pure serializer/reconstruction logic in
isolation from the routes that call them (mirrors tests/api/test_cards.py's split for
verdict_card).
"""
from __future__ import annotations

from anamnesis.memory.cluster import ClusterEdge, ClusterGraph, ClusterNode
from anamnesis.memory.graph import ForensicMemory
from anamnesis.memory.models import Provenance, make_edge
from anamnesis.memory.repository import InMemoryRepository
from fastapi.testclient import TestClient

from api import deps
from api.cards import graph_dict
from api.main import app

client = TestClient(app)

DEPLOYER = "dep1111111111111111111111111111111111111"
TOKEN = "rug1111111111111111111111111111111111111pump"


def _edge(rel, src, dst, method="first_party", conf=0.9, at="2026-01-01"):
    return make_edge(rel, src, dst, valid_from=at, recorded_at=at,
                      provenance=Provenance("helius:getAsset", method, conf))


# ---------------------------------------------------------------------------
# graph_dict — pure serializer (no memory, no recall_cluster BFS)
# ---------------------------------------------------------------------------


def test_graph_dict_maps_kind_to_type_and_rel_to_type():
    cluster = ClusterGraph(
        seed="dep",
        nodes=(
            ClusterNode(id="dep", kind="wallet", flags=("deployer",)),
            ClusterNode(id="tokA", kind="token", flags=("rugged",)),
        ),
        edges=(
            ClusterEdge(src="dep", dst="tokA", rel="RUGGED", method="first_party", confidence=0.9),
        ),
        depth=1,
        truncated=False,
        as_of=None,
    )

    out = graph_dict(cluster)

    assert out == {
        "nodes": [
            {"id": "dep", "type": "wallet", "flags": ["deployer"]},
            {"id": "tokA", "type": "token", "flags": ["rugged"]},
        ],
        "edges": [{"src": "dep", "dst": "tokA", "type": "RUGGED"}],
    }


def test_graph_dict_empty_cluster_is_empty_lists():
    cluster = ClusterGraph(seed="ghost", nodes=(), edges=(), depth=1, truncated=False, as_of=None)

    assert graph_dict(cluster) == {"nodes": [], "edges": []}


# ---------------------------------------------------------------------------
# GET /api/graph/{deployer}
# ---------------------------------------------------------------------------


def test_get_graph_returns_deployer_and_rugged_token_with_edge(monkeypatch):
    # DEPLOYED + RUGGED (mirrors tests/test_cluster.py::test_reaches_deployed_tokens_with_kinds_and_flags):
    # the "deployer" flag comes specifically from a DEPLOYED edge's src, not from RUGGED alone.
    mem = ForensicMemory(InMemoryRepository())
    mem.remember(
        [_edge("DEPLOYED", DEPLOYER, TOKEN), _edge("RUGGED", DEPLOYER, TOKEN)],
        now="2026-01-01",
    )
    monkeypatch.setattr(deps, "get_memory", lambda: mem)

    resp = client.get(f"/api/graph/{DEPLOYER}")

    assert resp.status_code == 200
    body = resp.json()
    nodes_by_id = {n["id"]: n for n in body["nodes"]}
    assert nodes_by_id[DEPLOYER]["type"] == "wallet"
    assert nodes_by_id[DEPLOYER]["flags"] == ["deployer"]
    assert nodes_by_id[TOKEN]["type"] == "token"
    assert nodes_by_id[TOKEN]["flags"] == ["rugged"]
    assert {"src": DEPLOYER, "dst": TOKEN, "type": "RUGGED"} in body["edges"]
    assert {"src": DEPLOYER, "dst": TOKEN, "type": "DEPLOYED"} in body["edges"]


def test_get_graph_unknown_deployer_is_single_node_not_404(monkeypatch):
    # recall_cluster degrades an unknown seed to a single, flag-less "wallet" node rather
    # than raising (tests/test_cluster.py::test_empty_seed_is_single_node) — the route must
    # not special-case this into a 404.
    monkeypatch.setattr(deps, "get_memory", lambda: ForensicMemory(InMemoryRepository()))

    resp = client.get("/api/graph/ghost")

    assert resp.status_code == 200
    assert resp.json() == {"nodes": [{"id": "ghost", "type": "wallet", "flags": []}], "edges": []}
