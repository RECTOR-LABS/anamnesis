from anamnesis.agent.actions import (
    assess_and_act,
    draft_alert,
    draft_for_mint,
    list_pending_alerts,
    watchlist_add,
    watchlist_mint,
)
from anamnesis.forensic.signals import LpAssessment, LpStatus, Signal, TokenProfile
from anamnesis.memory.alerts import InMemoryAlertStore
from anamnesis.memory.graph import ForensicMemory
from anamnesis.memory.models import Provenance as _Prov
from anamnesis.memory.models import make_edge
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
    assert len(current) == 1  # re-add is idempotent per (deployer, mint); no duplicate


def test_watchlist_re_add_decreasing_score_still_no_duplicate():
    # The standing entry is kept regardless of score direction. A decreasing-but-still-HIGH
    # re-assessment would slip past trust-based supersession (lower trust never retires the
    # prior), so idempotency — not supersession — is what keeps recall to one edge per pair.
    mem = ForensicMemory(InMemoryRepository())
    first = watchlist_add(mem, "dep", "mintZ", 0.95, "2026-06-27")
    again = watchlist_add(mem, "dep", "mintZ", 0.65, "2026-06-28")
    assert again.id == first.id  # same standing entry returned, not a new lower-trust edge
    current = [e for e in mem.recall("dep") if e.type == "WATCHLISTED" and e.dst == "mintZ"]
    assert len(current) == 1


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


def _rugger_memory():
    mem = ForensicMemory(InMemoryRepository())
    mem.remember(
        [make_edge("RUGGED", "ruggerX", "tokA", valid_from="2026-01-01",
                   recorded_at="2026-01-01", provenance=_Prov("helius:getAsset", "first_party", 0.95)),
         make_edge("RUGGED", "ruggerX", "tokB", valid_from="2026-01-05",
                   recorded_at="2026-01-05", provenance=_Prov("helius:getAsset", "first_party", 0.95))],
        now="2026-01-05",
    )
    return mem


def _clean_profile(deployer, mint="tokFresh"):
    return TokenProfile(mint=mint, deployer=deployer, mint_authority=None, freeze_authority=None,
                        lp=LpAssessment(LpStatus.SECURED), top_holder_pct=2.0, holder_count=300)


def test_assess_and_act_high_verdict_watchlists_and_drafts():
    # DoD: a remembered serial rugger's fresh, clean-looking token -> HIGH -> watchlist + alert.
    mem, store = _rugger_memory(), InMemoryAlertStore()
    out = assess_and_act(mem, store, lambda m: _clean_profile("ruggerX"), "tokFresh", "2026-06-27")
    assert out["level"] == "high" and out["acted"] is True
    assert out["watchlisted"]["deployer"] == "ruggerX"
    assert out["alert"]["mint"] == "tokFresh" and out["alert"]["status"] == "pending"
    assert [e for e in mem.recall("ruggerX") if e.type == "WATCHLISTED"]
    assert len(store.list_pending()) == 1


def test_assess_and_act_low_verdict_does_not_act():
    mem, store = ForensicMemory(InMemoryRepository()), InMemoryAlertStore()
    out = assess_and_act(mem, store, lambda m: _clean_profile("freshWallet", "m"), "m", "2026-06-27")
    assert out["level"] == "low" and out["acted"] is False
    assert out["watchlisted"] is None and out["alert"] is None
    assert store.list_pending() == []


def test_assess_and_act_preserves_verdict_when_write_fails():
    class _BoomStore:
        def add_draft(self, d):
            raise RuntimeError("mongo down")

        def list_pending(self):
            return []

        def get(self, i):
            return None

    out = assess_and_act(_rugger_memory(), _BoomStore(),
                         lambda m: _clean_profile("ruggerX"), "tokFresh", "2026-06-27")
    assert out["level"] == "high"          # verdict preserved despite the failed write
    assert out["acted"] is False and "error" in out


def test_list_pending_alerts_returns_queue():
    store = InMemoryAlertStore()
    draft_alert(store, _verdict(), "dep", "mintZ", "2026-06-27")
    out = list_pending_alerts(store)
    assert out["count"] == 1
    assert out["pending"][0]["mint"] == "mintZ" and out["pending"][0]["status"] == "pending"


def test_watchlist_mint_forces_watchlist_even_when_low():
    mem = ForensicMemory(InMemoryRepository())
    out = watchlist_mint(mem, lambda m: _clean_profile("freshWallet", "m"), "m", "2026-06-27")
    assert out["watchlisted"]["deployer"] == "freshWallet"
    assert [e for e in mem.recall("freshWallet") if e.type == "WATCHLISTED"]


def test_watchlist_mint_unresolved_deployer_is_a_noop():
    mem = ForensicMemory(InMemoryRepository())
    out = watchlist_mint(mem, lambda m: _clean_profile(None, "m"), "m", "2026-06-27")
    assert out["watchlisted"] is None and "note" in out


def test_draft_for_mint_drafts_regardless_of_threshold():
    mem, store = ForensicMemory(InMemoryRepository()), InMemoryAlertStore()
    out = draft_for_mint(mem, store, lambda m: _clean_profile("freshWallet", "m"), "m", "2026-06-27")
    assert out["alert"]["mint"] == "m" and out["alert"]["status"] == "pending"
    assert len(store.list_pending()) == 1
