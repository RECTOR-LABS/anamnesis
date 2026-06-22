from anamnesis.forensic.signals import TokenProfile, assess_token_signals


def _clean() -> TokenProfile:
    return TokenProfile(
        mint="m", deployer="d", mint_authority=None, freeze_authority=None,
        lp_secured=True, top_holder_pct=3.0, holder_count=500,
    )


def test_clean_token_has_no_signals():
    assert assess_token_signals(_clean()) == []


def test_active_authorities_and_unsecured_lp_flag_high():
    p = TokenProfile(
        mint="m", deployer="d", mint_authority="d", freeze_authority="d",
        lp_secured=False, top_holder_pct=3.0, holder_count=10,
    )
    codes = {s.code for s in assess_token_signals(p)}
    assert {"MINT_AUTHORITY_ACTIVE", "FREEZE_AUTHORITY_ACTIVE", "LP_NOT_SECURED"} <= codes
    assert all(
        s.severity == "high"
        for s in assess_token_signals(p)
        if s.code != "HOLDER_CONCENTRATION"
    )


def test_holder_concentration_threshold():
    p = TokenProfile(
        mint="m", deployer="d", mint_authority=None, freeze_authority=None,
        lp_secured=True, top_holder_pct=25.0, holder_count=4,
    )
    assert any(s.code == "HOLDER_CONCENTRATION" for s in assess_token_signals(p))
