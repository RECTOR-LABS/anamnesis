from anamnesis.agent.actions import watchlist_add
from anamnesis.memory.graph import ForensicMemory
from anamnesis.memory.repository import InMemoryRepository


def test_watchlist_add_writes_derived_edge_and_recalls():
    mem = ForensicMemory(InMemoryRepository())
    edge = watchlist_add(mem, "dep", "mintZ", 0.72, "2026-06-27")
    assert edge.type == "WATCHLISTED" and edge.src == "dep" and edge.dst == "mintZ"
    assert edge.provenance.method == "derived" and edge.provenance.source == "assess_risk"
    assert abs(edge.provenance.confidence - 0.72) < 1e-9
    assert any(e.type == "WATCHLISTED" and e.dst == "mintZ" for e in mem.recall("dep"))


def test_watchlist_does_not_inflate_risk_no_feedback_loop():
    mem = ForensicMemory(InMemoryRepository())
    watchlist_add(mem, "dep", "mintZ", 1.0, "2026-06-27")
    # WATCHLISTED is not a scored type -> memory risk stays 0 (it records, it does not accuse)
    assert mem.trust_weighted_risk(mem.recall("dep")) == 0.0


def test_watchlist_re_add_supersedes_not_duplicates():
    mem = ForensicMemory(InMemoryRepository())
    watchlist_add(mem, "dep", "mintZ", 0.7, "2026-06-27")
    watchlist_add(mem, "dep", "mintZ", 0.9, "2026-06-28")
    current = [e for e in mem.recall("dep") if e.type == "WATCHLISTED" and e.dst == "mintZ"]
    assert len(current) == 1  # higher-trust re-add supersedes the prior; no duplicate
