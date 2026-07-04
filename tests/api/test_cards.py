from api.cards import verdict_card


def test_verdict_card_shapes_high_from_memory():
    result = {  # shape returned by assess_and_act: verdict_to_dict(...) + acted/watchlisted/alert
        "level": "HIGH", "score": 0.8511, "rationale": "…",
        "signals": [
            {"code": "HOLDER_CONCENTRATION", "severity": "medium", "detail": "top holder 97.8%"}
        ],
        "remembered": [
            {"type": "RUGGED", "dst": "3qFSo", "valid_from": "2025-11-16", "method": "first_party"}
        ],
        "acted": True, "watchlisted": {"deployer": "sF2ww", "mint": "GYaS"}, "alert": {"severity": "HIGH"},
    }
    card = verdict_card(result, mint="GYaS", deployer="sF2ww")
    assert card["level"] == "HIGH"
    assert round(card["score"], 4) == 0.8511
    assert card["provenance"]["first_party"] == 0.85          # rounded band
    assert card["provenance"]["derived"] is None              # context-only tiers null
    assert {r["mint"] for r in card["memory_rugs"]} == {"3qFSo"}
    assert card["signals"][0]["code"] == "HOLDER_CONCENTRATION"
    assert card["mint"] == "GYaS"
    assert card["deployer"] == "sF2ww"
    # passthrough keys carry the result's values verbatim (guards a typo'd .get("...") key
    # silently yielding None instead of raising).
    assert card["rationale"] == result["rationale"]
    assert card["acted"] == result["acted"]
    assert card["watchlisted"] == result["watchlisted"]
    assert card["alert"] == result["alert"]


def test_verdict_card_rugs_excludes_non_qualifying_edges():
    # _rugs is the file's one real piece of conditional logic: it backs the provenance-trust
    # distinction (first-party vs. derived/claimed) that the UI relies on when it labels
    # memory_rugs as first-party-verified. A mixed remembered list proves _rugs actually
    # EXCLUDES edges that fail either half of its `type == "RUGGED" and method == "first_party"`
    # check, not just that it includes the ones that pass.
    result = {
        "level": "HIGH", "score": 0.9, "rationale": "…", "signals": [],
        "remembered": [
            {"type": "RUGGED", "dst": "3qFSo", "valid_from": "2025-11-16", "method": "first_party"},
            # wrong type, derived method: neither half of the qualifying check passes
            {"type": "WATCHLISTED", "dst": "wrongType", "valid_from": "2025-11-01", "method": "derived"},
            # right type, wrong method: RUGGED but not first-party trust
            {"type": "RUGGED", "dst": "wrongMethod", "valid_from": "2025-10-01", "method": "derived"},
        ],
        "acted": False, "watchlisted": None, "alert": None,
    }
    card = verdict_card(result, mint="m3", deployer=None)
    assert {r["mint"] for r in card["memory_rugs"]} == {"3qFSo"}
    assert len(card["memory_rugs"]) == 1


def test_verdict_card_medium_level_has_first_party_score():
    result = {
        "level": "medium", "score": 0.4321, "rationale": "…", "signals": [], "remembered": [],
        "acted": False, "watchlisted": None, "alert": None,
    }
    card = verdict_card(result, mint="m4", deployer=None)
    assert card["level"] == "MEDIUM"
    assert card["provenance"]["first_party"] == round(0.4321, 2)


def test_verdict_card_normalizes_lowercase_engine_level_for_provenance_gate():
    # anamnesis.risk.Verdict.level is lowercase ("low"|"medium"|"high") in the real engine
    # (compose_verdict in src/anamnesis/risk.py, passed through verbatim by verdict_to_dict).
    # Every existing engine test (test_risk.py, test_actions.py, test_agent_tools.py,
    # test_serialize.py) confirms lowercase is the real, consistent convention. Without
    # normalization here, the provenance gate below (`level in ("HIGH", "MEDIUM")`) would
    # silently never fire against real assess_and_act output, permanently hiding the
    # first-party score tier for genuine HIGH/MEDIUM verdicts.
    result = {
        "level": "high", "score": 0.71, "rationale": "…", "signals": [], "remembered": [],
        "acted": False, "watchlisted": None, "alert": None,
    }
    card = verdict_card(result, mint="m1", deployer=None)
    assert card["level"] == "HIGH"
    assert card["provenance"]["first_party"] == 0.71


def test_verdict_card_low_level_has_no_first_party_score():
    result = {
        "level": "low", "score": 0.05, "rationale": "…", "signals": [], "remembered": [],
        "acted": False, "watchlisted": None, "alert": None,
    }
    card = verdict_card(result, mint="m2", deployer=None)
    assert card["level"] == "LOW"
    assert card["provenance"]["first_party"] is None
    assert card["provenance"]["claimed"] is None
