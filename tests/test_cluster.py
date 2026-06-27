from anamnesis.memory.cluster import recall_cluster
from anamnesis.memory.graph import ForensicMemory
from anamnesis.memory.models import Provenance, make_edge
from anamnesis.memory.repository import InMemoryRepository


def _e(rel, src, dst, method="first_party", conf=0.9, at="2026-01-01"):
    return make_edge(rel, src, dst, valid_from=at, recorded_at=at,
                     provenance=Provenance("helius:getAsset", method, conf))


def _mem(*edges):
    m = ForensicMemory(InMemoryRepository())
    if edges:
        m.remember(list(edges), now="2026-01-01")
    return m


def test_reaches_deployed_tokens_with_kinds_and_flags():
    mem = _mem(_e("DEPLOYED", "dep", "tokA"), _e("RUGGED", "dep", "tokA"),
               _e("WATCHLISTED", "dep", "tokFresh", method="derived", conf=0.7))
    ids = {n.id: n for n in recall_cluster(mem, "dep", depth=1).nodes}
    assert set(ids) == {"dep", "tokA", "tokFresh"}
    assert ids["dep"].kind == "wallet" and "deployer" in ids["dep"].flags
    assert ids["tokA"].kind == "token" and "rugged" in ids["tokA"].flags
    assert "watchlisted" in ids["tokFresh"].flags


def test_depth_bounds_the_walk():
    mem = _mem(_e("SAME_CLUSTER", "dep", "peer"), _e("DEPLOYED", "peer", "tokP"))
    assert {n.id for n in recall_cluster(mem, "dep", depth=1).nodes} == {"dep", "peer"}
    assert {n.id for n in recall_cluster(mem, "dep", depth=2).nodes} == {"dep", "peer", "tokP"}


def test_undirected_reaches_funding_and_peers_with_kinds():
    mem = _mem(_e("FUNDED_BY", "dep", "cex:binance"), _e("SAME_CLUSTER", "dep", "peer"))
    ids = {n.id: n for n in recall_cluster(mem, "dep", depth=1).nodes}
    assert ids["cex:binance"].kind == "funding" and ids["peer"].kind == "wallet"


def test_rel_types_filter():
    mem = _mem(_e("DEPLOYED", "dep", "tokA"), _e("FUNDED_BY", "dep", "cex"))
    g = recall_cluster(mem, "dep", depth=1, rel_types=frozenset({"DEPLOYED"}))
    assert {n.id for n in g.nodes} == {"dep", "tokA"}
    assert all(e.rel == "DEPLOYED" for e in g.edges)


def test_dedups_and_is_cycle_safe():
    mem = _mem(_e("SAME_CLUSTER", "a", "b"), _e("SAME_CLUSTER", "b", "a"))
    g = recall_cluster(mem, "a", depth=3)
    assert {n.id for n in g.nodes} == {"a", "b"}
    assert len(g.edges) == len({(e.src, e.dst, e.rel) for e in g.edges})


def test_empty_seed_is_single_node():
    g = recall_cluster(_mem(), "ghost", depth=2)
    assert [n.id for n in g.nodes] == ["ghost"] and g.edges == () and g.truncated is False


def test_size_cap_sets_truncated():
    mem = _mem(*[_e("DEPLOYED", "hub", f"tok{i}") for i in range(20)])
    g = recall_cluster(mem, "hub", depth=1, max_nodes=5)
    assert g.truncated is True and len(g.nodes) <= 5


def test_as_of_excludes_later_edges():
    mem = ForensicMemory(InMemoryRepository())
    mem.remember([_e("DEPLOYED", "dep", "tokA", at="2026-01-01")], now="2026-01-01")
    mem.remember([_e("RUGGED", "dep", "tokA", at="2026-03-01")], now="2026-03-01")
    early = recall_cluster(mem, "dep", depth=1, as_of="2026-02-01")
    assert {(e.src, e.dst, e.rel) for e in early.edges} == {("dep", "tokA", "DEPLOYED")}
    assert early.as_of == "2026-02-01"
