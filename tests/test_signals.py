from anamnesis.forensic.signals import (
    LpAssessment,
    LpEvidence,
    LpStatus,
    TokenProfile,
    assess_token_signals,
)


def _profile(lp, **kw):
    base = dict(
        mint="m", deployer="d", mint_authority=None, freeze_authority=None,
        lp=lp, top_holder_pct=3.0, holder_count=500,
    )
    base.update(kw)
    return TokenProfile(**base)


def test_clean_token_has_no_signals():
    assert assess_token_signals(_profile(LpAssessment(LpStatus.SECURED))) == []


def test_active_authorities_and_unsecured_lp_flag_high():
    ev = [LpEvidence("raydium_v4", "P", "L", "withdrawable", False, "d", 50_000.0)]
    p = _profile(LpAssessment(LpStatus.NOT_SECURED, ev),
                 mint_authority="d", freeze_authority="d", holder_count=10)
    codes = {s.code for s in assess_token_signals(p)}
    assert {"MINT_AUTHORITY_ACTIVE", "FREEZE_AUTHORITY_ACTIVE", "LP_NOT_SECURED"} <= codes
    assert all(
        s.severity == "high"
        for s in assess_token_signals(p)
        if s.code != "HOLDER_CONCENTRATION"
    )


def test_holder_concentration_threshold():
    p = _profile(LpAssessment(LpStatus.SECURED), top_holder_pct=25.0, holder_count=4)
    assert any(s.code == "HOLDER_CONCENTRATION" for s in assess_token_signals(p))


def test_unknown_lp_flags_low_unverified_not_high():
    sigs = assess_token_signals(_profile(LpAssessment(LpStatus.UNKNOWN)))
    lp = [s for s in sigs if s.code == "LP_UNVERIFIED"]
    assert lp and lp[0].severity == "low"
    assert not any(s.code == "LP_NOT_SECURED" for s in sigs)


def test_secured_lp_emits_no_lp_signal():
    sigs = assess_token_signals(_profile(LpAssessment(LpStatus.SECURED)))
    assert not any(s.code in ("LP_NOT_SECURED", "LP_UNVERIFIED") for s in sigs)


def test_not_secured_detail_names_largest_rug_vector_pool():
    ev = [
        LpEvidence("raydium_v4", "POOL_SMALL", "L", "withdrawable", False, "d", 1_500.0),
        LpEvidence("pumpswap", "POOL_BIG", "L", "withdrawable", False, "d", 90_000.0),
    ]
    sigs = assess_token_signals(_profile(LpAssessment(LpStatus.NOT_SECURED, ev)))
    detail = next(s.detail for s in sigs if s.code == "LP_NOT_SECURED")
    assert "POOL_BIG" in detail  # the largest-liquidity unsecured pool is named
