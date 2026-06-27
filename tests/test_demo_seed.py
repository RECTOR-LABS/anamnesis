"""Tests for the A.10 demo seed (pure core in anamnesis.demo_seed).

No live services: the scoring/idempotency tests run against mongomock, matching the suite.
"""
import pytest

from anamnesis.demo_seed import (
    DEMO_MINT,
    DEPLOYER,
    PRIOR_RUGS,
    RugSeed,
    assert_resettable,
    build_seed_edges,
)
from anamnesis.memory.graph import ForensicMemory
from anamnesis.memory.mongo_store import MongoRepository

_TWO_RUGS = [
    RugSeed("mintA", valid_from="2025-11-16", recorded_at="2026-06-05"),
    RugSeed("mintB", valid_from="2025-12-05", recorded_at="2026-06-15"),
]


def _mongo_memory() -> ForensicMemory:
    mongomock = pytest.importorskip("mongomock")
    return ForensicMemory(MongoRepository(mongomock.MongoClient(), "anamnesis_test"))


def test_build_seed_edges_emits_first_party_rugged_and_deployed_per_rug():
    edges = build_seed_edges("DEP", _TWO_RUGS)
    rugged = [e for e in edges if e.type == "RUGGED"]
    deployed = [e for e in edges if e.type == "DEPLOYED"]
    assert {e.dst for e in rugged} == {"mintA", "mintB"}
    assert {e.dst for e in deployed} == {"mintA", "mintB"}
    assert all(e.src == "DEP" for e in edges)
    assert all(e.provenance.method == "first_party" for e in edges)  # must score, not 'claimed'
    assert all(e.provenance.confidence == 1.0 for e in rugged)
    a = next(e for e in rugged if e.dst == "mintA")  # bi-temporal split: on-chain before learned
    assert a.valid_from < a.recorded_at


def test_two_distinct_rugs_reach_high_from_memory():
    # The tuning the whole demo rests on: 2 distinct first-party rugs clear the HIGH band (0.6).
    mem = _mongo_memory()
    mem.remember(build_seed_edges("DEP", _TWO_RUGS), now="2026-06-27")
    assert mem.trust_weighted_risk(mem.recall_deployer_history("DEP")) >= 0.6


def test_deployed_edges_are_recalled_but_do_not_inflate_score():
    # DEPLOYED is context (recalled) but not in RISK_WEIGHTS, so a single rug + its DEPLOYED edge
    # stays MEDIUM (one rug), proving DEPLOYED never lends risk.
    mem = _mongo_memory()
    mem.remember(build_seed_edges("DEP", _TWO_RUGS[:1]), now="2026-06-27")
    history = mem.recall_deployer_history("DEP")
    assert {e.type for e in history} == {"RUGGED", "DEPLOYED"}
    assert 0.3 <= mem.trust_weighted_risk(history) < 0.6  # one rug = MEDIUM, not HIGH


def test_seed_is_idempotent():
    mem = _mongo_memory()
    edges = build_seed_edges("DEP", _TWO_RUGS[:1])
    mem.remember(edges, now="2026-06-27")
    mem.remember(edges, now="2026-06-27")  # re-run before a fresh take
    assert len(mem.recall("DEP")) == len(edges)  # deterministic ids -> no duplicates


def test_shipped_constants_reach_high():
    # Guard the actual demo payload: the committed DEPLOYER/PRIOR_RUGS must themselves hit HIGH,
    # and the live demo mint must not be one of the seeded rugs (it is discovered live).
    mem = _mongo_memory()
    mem.remember(build_seed_edges(DEPLOYER, PRIOR_RUGS), now="2026-06-27")
    assert mem.trust_weighted_risk(mem.recall_deployer_history(DEPLOYER)) >= 0.6
    assert len(PRIOR_RUGS) >= 2
    assert DEMO_MINT not in {r.mint for r in PRIOR_RUGS}


def test_reset_guard_allows_demo_db_refuses_prodlike():
    assert_resettable("anamnesis")        # the demo/dev db — allowed (no raise)
    assert_resettable("anamnesis_test")
    for bad in ("anamnesis_prod", "production", "prod", "mainnet_memory", "live_db"):
        with pytest.raises(SystemExit):
            assert_resettable(bad)
