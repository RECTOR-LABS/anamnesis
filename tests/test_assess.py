from anamnesis.assess import assess_risk
from anamnesis.forensic.signals import TokenProfile
from anamnesis.memory.graph import ForensicMemory
from anamnesis.memory.models import Edge, Provenance, make_edge_id
from anamnesis.memory.repository import InMemoryRepository


def _edge(type_, src, dst, rec, conf=0.95, source="helius:getAsset"):
    return Edge(
        make_edge_id(type_, src, dst, rec), type_, src, dst,
        rec, None, rec, None, Provenance(source, "first_party", conf),
    )


def _profile(deployer, **kw):
    base = dict(
        mint="m", deployer=deployer, mint_authority=None, freeze_authority=None,
        lp_secured=True, top_holder_pct=2.0, holder_count=300,
    )
    base.update(kw)
    return TokenProfile(**base)


def test_serial_rugger_fresh_token_flagged_high_from_memory():
    # The compounding-memory payoff: a deployer we have seen rug twice before,
    # whose brand-new token looks clean on-chain, is still flagged HIGH on sight.
    mem = ForensicMemory(InMemoryRepository())
    mem.remember(
        [
            _edge("DEPLOYED", "ruggerX", "tok1", "2026-01-01"),
            _edge("RUGGED", "ruggerX", "tok1", "2026-01-05"),
            _edge("DEPLOYED", "ruggerX", "tok2", "2026-02-01"),
            _edge("RUGGED", "ruggerX", "tok2", "2026-02-05"),
        ],
        now="2026-02-05",
    )
    fresh = _profile("ruggerX", mint="tok3")  # clean live signals
    verdict = assess_risk(fresh, mem)
    assert verdict.level == "high"  # memory alone drives HIGH
    assert verdict.remembered  # cites the remembered rug history


def test_clean_token_unknown_deployer_is_low():
    mem = ForensicMemory(InMemoryRepository())
    assert assess_risk(_profile("freshWallet"), mem).level == "low"


def test_live_high_signals_alone_drive_high_without_memory():
    mem = ForensicMemory(InMemoryRepository())
    risky = _profile(
        "w", mint_authority="w", freeze_authority="w", lp_secured=False, top_holder_pct=40.0
    )
    verdict = assess_risk(risky, mem)
    assert verdict.level == "high"
    assert verdict.cited_signals


def test_unresolved_deployer_skips_memory_recall():
    mem = ForensicMemory(InMemoryRepository())
    assert assess_risk(_profile(None), mem).level == "low"
