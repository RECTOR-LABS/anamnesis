"""HTTP + pure-function tests for GET /api/graph/{deployer} and GET /api/price/{mint}.

Route tests use FastAPI's TestClient with api.deps.get_memory / api.deps.get_dex
monkeypatched to network-free fakes (an InMemoryRepository-backed ForensicMemory; a fake
DexScreener client) — no Mongo, no HTTP. graph_dict/price_points are also each exercised
directly against hand-built inputs, proving the pure serializer/reconstruction logic in
isolation from the routes that call them (mirrors tests/api/test_cards.py's split for
verdict_card).
"""
from __future__ import annotations

from datetime import datetime, timezone

from anamnesis.forensic.pools import AggregatorError
from anamnesis.memory.cluster import ClusterEdge, ClusterGraph, ClusterNode
from anamnesis.memory.graph import ForensicMemory
from anamnesis.memory.models import Provenance, make_edge
from anamnesis.memory.repository import InMemoryRepository
from fastapi.testclient import TestClient

from api import deps
from api.cards import graph_dict, price_points
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


# ---------------------------------------------------------------------------
# price_points — pure reconstruction from DexScreener priceChange buckets
# ---------------------------------------------------------------------------

NOW = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)


def test_price_points_reconstructs_oldest_to_newest_ending_at_current_price():
    pairs = [{
        "priceUsd": "2.0",
        "priceChange": {"h24": -50.0, "h6": -20.0, "h1": 25.0, "m5": 0.0},
        "liquidity": {"usd": 10000.0},
    }]

    points = price_points(pairs, NOW)

    assert len(points) == 5  # h24, h6, h1, m5, + the always-appended current point
    assert [p["t"] for p in points] == sorted(p["t"] for p in points)  # oldest -> newest
    assert points[0]["price"] == 2.0 / (1 + -50.0 / 100)   # h24 reconstruction
    assert points[1]["price"] == 2.0 / (1 + -20.0 / 100)   # h6
    assert points[2]["price"] == 2.0 / (1 + 25.0 / 100)    # h1
    assert points[3]["price"] == 2.0 / (1 + 0.0 / 100)     # m5
    assert points[-1] == {"t": NOW.isoformat(), "price": 2.0}  # ends at current price


def test_price_points_picks_highest_liquidity_pair():
    pairs = [
        {"priceUsd": "1.0", "priceChange": {"h24": 0.0}, "liquidity": {"usd": 5.0}},
        {"priceUsd": "9.0", "priceChange": {"h24": 0.0}, "liquidity": {"usd": 999999.0}},
    ]

    points = price_points(pairs, NOW)

    assert points[-1]["price"] == 9.0


def test_price_points_empty_pairs_is_empty_list():
    assert price_points([], NOW) == []


def test_price_points_missing_price_usd_is_empty_list():
    pairs = [{"priceUsd": None, "priceChange": {"h24": 1.0}, "liquidity": {"usd": 1.0}}]

    assert price_points(pairs, NOW) == []


def test_price_points_skips_missing_change_buckets_and_guards_divide_by_zero():
    # h24/h1 are absent entirely (skipped, not a KeyError); m5 == -100% would divide by
    # zero, so that bucket must be dropped rather than raising or emitting inf/nan.
    pairs = [{
        "priceUsd": "1.0",
        "priceChange": {"h6": 10.0, "m5": -100.0},
        "liquidity": {"usd": 1.0},
    }]

    points = price_points(pairs, NOW)

    assert len(points) == 2  # h6 reconstruction + the always-appended current point
    assert points[0]["price"] == 1.0 / (1 + 10.0 / 100)
    assert points[-1]["price"] == 1.0


def test_price_points_unparseable_price_usd_is_empty_list():
    # Distinct from the None/TypeError branch above: "N/A" is a str, so float() raises
    # ValueError, not TypeError — both must land in the same guard, not raise past it.
    pairs = [{"priceUsd": "N/A", "priceChange": {"h24": 1.0}, "liquidity": {"usd": 1.0}}]

    assert price_points(pairs, NOW) == []


def test_price_points_non_dict_price_change_yields_only_current_point():
    # Off-spec upstream data (see DexScreenerClient.token_pairs, which validates only the
    # top-level list shape): a truthy non-dict priceChange must not raise AttributeError
    # from `.get` — it degrades to "no reconstructed points" while the current-price point
    # is still appended.
    pairs = [{"priceUsd": "1.5", "priceChange": "not-a-dict", "liquidity": {"usd": 1.0}}]

    points = price_points(pairs, NOW)

    assert points == [{"t": NOW.isoformat(), "price": 1.5}]


def test_price_points_non_dict_liquidity_does_not_crash_selection():
    # A truthy non-dict liquidity must contribute 0 to the top-liquidity `max(...)` instead
    # of raising AttributeError inside the key function.
    pairs = [{"priceUsd": "4.0", "priceChange": {"h24": 0.0}, "liquidity": "not-a-dict"}]

    points = price_points(pairs, NOW)

    assert points[-1]["price"] == 4.0


# ---------------------------------------------------------------------------
# GET /api/price/{mint}
# ---------------------------------------------------------------------------


class _FakeDex:
    """Stands in for DexScreenerClient: returns fixed pairs, or raises like the real
    client's token_pairs does on a transport/shape failure."""

    def __init__(self, pairs=None, error=None):
        self._pairs = pairs
        self._error = error

    def token_pairs(self, mint: str) -> list[dict]:
        if self._error is not None:
            raise self._error
        return self._pairs


def test_get_price_returns_points_for_known_mint(monkeypatch):
    pairs = [{
        "priceUsd": "3.0",
        "priceChange": {"h24": -10.0, "h6": -5.0, "h1": 2.0, "m5": 0.0},
        "liquidity": {"usd": 42.0},
    }]
    monkeypatch.setattr(deps, "get_dex", lambda: _FakeDex(pairs=pairs))

    resp = client.get("/api/price/someMint")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["points"]) == 5
    assert body["points"][-1]["price"] == 3.0


def test_get_price_empty_pairs_is_empty_points(monkeypatch):
    monkeypatch.setattr(deps, "get_dex", lambda: _FakeDex(pairs=[]))

    resp = client.get("/api/price/someMint")

    assert resp.status_code == 200
    assert resp.json() == {"points": []}


def test_get_price_missing_price_usd_is_empty_points(monkeypatch):
    pairs = [{"priceUsd": None, "priceChange": {"h24": 1.0}, "liquidity": {"usd": 1.0}}]
    monkeypatch.setattr(deps, "get_dex", lambda: _FakeDex(pairs=pairs))

    resp = client.get("/api/price/someMint")

    assert resp.status_code == 200
    assert resp.json() == {"points": []}


def test_get_price_aggregator_error_is_empty_points_not_500(monkeypatch):
    monkeypatch.setattr(deps, "get_dex", lambda: _FakeDex(error=AggregatorError("dexscreener down")))

    resp = client.get("/api/price/someMint")

    assert resp.status_code == 200
    assert resp.json() == {"points": []}


def test_get_price_non_dict_price_change_is_200_not_500(monkeypatch):
    # Reproduces the reviewer's finding: a truthy non-dict priceChange from an off-spec
    # upstream pair used to raise AttributeError inside price_points, and since price_points
    # is called outside the route's `except AggregatorError`, that became an unhandled 500 —
    # violating this endpoint's documented never-500 contract (see api/routes/price.py's
    # module docstring). TestClient re-raises server errors by default, so a regression here
    # fails this test rather than silently reporting 500 in the JSON body.
    pairs = [{"priceUsd": "1.0", "priceChange": "not-a-dict", "liquidity": {"usd": 1.0}}]
    monkeypatch.setattr(deps, "get_dex", lambda: _FakeDex(pairs=pairs))

    resp = client.get("/api/price/someMint")

    assert resp.status_code == 200
    points = resp.json()["points"]
    assert len(points) == 1  # no reconstructed buckets, just the current-price point
    assert points[0]["price"] == 1.0
    assert isinstance(points[0]["t"], str) and points[0]["t"]  # route-clock timestamp, not asserted exactly


def test_get_price_non_dict_liquidity_is_200_not_500(monkeypatch):
    # Same contract violation, triggered even earlier: a truthy non-dict liquidity raises
    # AttributeError inside the max(...) key function used to pick the top-liquidity pair,
    # before price_points ever reaches the priceChange handling.
    pairs = [{"priceUsd": "1.0", "priceChange": {"h24": 0.0}, "liquidity": "not-a-dict"}]
    monkeypatch.setattr(deps, "get_dex", lambda: _FakeDex(pairs=pairs))

    resp = client.get("/api/price/someMint")

    assert resp.status_code == 200
    assert len(resp.json()["points"]) == 2
