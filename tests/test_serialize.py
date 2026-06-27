from anamnesis.agent.serialize import draft_to_dict, verdict_to_dict
from anamnesis.memory.alerts import AlertDraft
from anamnesis.risk import Verdict


def test_verdict_to_dict_rounds_and_lists():
    v = Verdict(level="high", score=0.7234, rationale="r")
    out = verdict_to_dict(v)
    assert out["level"] == "high" and out["score"] == 0.7234
    assert out["signals"] == [] and out["remembered"] == []


def test_draft_to_dict_roundtrips_fields():
    d = AlertDraft(id="a1", deployer="dep", mint="m", severity="high", score=0.72,
                   rationale="r", evidence=["e1"], message="msg", status="pending",
                   created_at="2026-06-27")
    out = draft_to_dict(d)
    assert out["id"] == "a1" and out["mint"] == "m" and out["status"] == "pending"
    assert out["evidence"] == ["e1"]
