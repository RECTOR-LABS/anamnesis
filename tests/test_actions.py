from anamnesis.agent.actions import draft_alert, watchlist_add
from anamnesis.forensic.signals import Signal
from anamnesis.memory.alerts import InMemoryAlertStore
from anamnesis.memory.graph import ForensicMemory
from anamnesis.memory.repository import InMemoryRepository
from anamnesis.risk import Verdict


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


def _verdict():
    return Verdict(
        level="high", score=0.72, rationale="deployer has remembered prior rug history",
        cited_signals=[Signal("MINT_AUTHORITY_ACTIVE", "high", "supply can be inflated")],
        remembered=[],
    )


def test_draft_alert_builds_and_persists_pending():
    store = InMemoryAlertStore()
    d = draft_alert(store, _verdict(), "dep", "mintZ", "2026-06-27")
    assert d.severity == "high" and d.mint == "mintZ" and d.status == "pending"
    assert any("MINT_AUTHORITY_ACTIVE" in line for line in d.evidence)
    assert "mintZ" in d.message and "0.72" in d.message
    assert store.list_pending() == [d]


def test_draft_alert_idempotent_per_deployer_mint():
    store = InMemoryAlertStore()
    draft_alert(store, _verdict(), "dep", "mintZ", "2026-06-27")
    draft_alert(store, _verdict(), "dep", "mintZ", "2026-06-28")
    assert len(store.list_pending()) == 1
