from anamnesis.forensic.signals import LpAssessment, LpEvidence, LpStatus


def test_lp_assessment_defaults_to_empty_evidence():
    a = LpAssessment(status=LpStatus.UNKNOWN)
    assert a.status is LpStatus.UNKNOWN
    assert a.evidence == []


def test_lp_status_is_json_friendly_string():
    assert LpStatus.SECURED.value == "secured"
    assert LpStatus.NOT_SECURED.value == "not_secured"


def test_lp_evidence_optional_fields_default_none():
    e = LpEvidence(
        venue="raydium_v4", pool="P", lp_mint="L", method="lp_mint_burned",
        secured=True, detail="d",
    )
    assert e.liquidity_usd is None and e.citation is None
