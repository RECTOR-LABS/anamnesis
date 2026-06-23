from anamnesis.forensic.signals import Signal
from anamnesis.risk import compose_verdict


def test_memory_hit_on_repeat_rugger_forces_high():
    # No live signals, but memory says this deployer rugged before -> still HIGH.
    v = compose_verdict(signals=[], memory_edges=["<edge>"], memory_risk=0.8)
    assert v.level == "high"
    assert v.remembered  # cites the remembered history


def test_clean_token_no_memory_is_low():
    v = compose_verdict(signals=[], memory_edges=[], memory_risk=0.0)
    assert v.level == "low"


def test_live_high_signals_raise_level():
    sigs = [Signal("LP_NOT_SECURED", "high", "x"), Signal("MINT_AUTHORITY_ACTIVE", "high", "y")]
    v = compose_verdict(signals=sigs, memory_edges=[], memory_risk=0.0)
    assert v.level in ("medium", "high")
    assert v.cited_signals


def test_medium_memory_verdict_has_consistent_rationale():
    # A MEDIUM verdict driven by partial remembered risk must not carry the
    # "no significant risk" rationale — level and explanation must agree.
    v = compose_verdict(signals=[], memory_edges=[], memory_risk=0.5)
    assert v.level == "medium"
    assert "no significant risk" not in v.rationale
    assert v.rationale  # explains the partial history
