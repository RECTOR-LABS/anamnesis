import pytest

from anamnesis.memory.graph import ForensicMemory
from anamnesis.memory.models import Edge, Provenance, make_edge_id
from anamnesis.memory.repository import InMemoryRepository


def _edge(type, src, dst, rec, conf=0.95, source="helius:getAsset", method="first_party") -> Edge:
    return Edge(
        make_edge_id(type, src, dst, rec), type, src, dst,
        rec, None, rec, None, Provenance(source, method, conf),
    )


def test_repeat_deployer_history_is_recalled(repo):
    mem = ForensicMemory(repo)
    mem.remember(
        [_edge("DEPLOYED", "ruggER", "tok1", "2026-02-01"),
         _edge("RUGGED", "ruggER", "tok1", "2026-02-09")],
        now="2026-02-09",
    )
    hist = mem.recall_deployer_history("ruggER")
    assert {e.type for e in hist} == {"DEPLOYED", "RUGGED"}


def test_supersession_hides_prior_belief_on_recall(repo):
    # remember() supersedes a prior (type, dst) belief from the SAME source; the
    # superseded edge drops out of the current view. Runs on whichever backend
    # --store selects, so the find -> mutate prior -> re-upsert path is proven on
    # the Mongo store too.
    mem = ForensicMemory(repo)
    mem.remember([_edge("RUGGED", "wallet1", "tok1", "2026-02-01")], now="2026-02-01")
    mem.remember([_edge("RUGGED", "wallet1", "tok1", "2026-02-10")], now="2026-02-10")
    current = mem.recall("wallet1")
    assert len(current) == 1
    assert current[0].recorded_at == "2026-02-10"


def test_extra_sources_for_same_token_do_not_change_risk():
    # The poisoning lever v3 removes: `provenance.source` is a forgeable free string.
    # Three sources reporting the SAME (type, dst) is one fact, not corroboration —
    # so adding sources for the same token must NOT move the score (only distinct
    # first-party rugged tokens can).
    mem = ForensicMemory(InMemoryRepository())
    one_source = [_edge("RUGGED", "w", "t", "2026-02-01")]
    three_sources = one_source + [
        _edge("RUGGED", "w", "t", "2026-02-01", source="rpc:largestAccounts"),
        _edge("RUGGED", "w", "t", "2026-02-01", source="enhanced:tx"),
    ]
    assert mem.trust_weighted_risk(three_sources) == mem.trust_weighted_risk(one_source)


def test_distinct_first_party_tokens_raise_risk():
    # The genuine serial-rugger signal: more distinct first-party rugged tokens
    # (distinct dst) => higher risk.
    mem = ForensicMemory(InMemoryRepository())
    one = [_edge("RUGGED", "w", "tA", "2026-02-01")]
    two = one + [_edge("RUGGED", "w", "tB", "2026-02-02")]
    assert mem.trust_weighted_risk(two) > mem.trust_weighted_risk(one)


def test_uncorroborated_low_confidence_claim_cannot_dominate():
    mem = ForensicMemory(InMemoryRepository())
    poison = [_edge("SAME_CLUSTER", "victim", "badguy", "2026-02-01",
                    conf=0.15, source="claimed:dust")]
    assert mem.trust_weighted_risk(poison) < 0.2  # seeded breadcrumb can't flip a verdict


def test_corroborated_rug_outweighs_poison_cluster():
    mem = ForensicMemory(InMemoryRepository())
    rug = [_edge("RUGGED", "w", "t", "2026-02-01", conf=0.9, source="helius:getAsset"),
           _edge("RUGGED", "w", "t", "2026-02-01", conf=0.9, source="rpc:largestAccounts")]
    poison = [_edge("SAME_CLUSTER", "w", "x", "2026-02-01", conf=0.1, source="claimed:dust")]
    assert mem.trust_weighted_risk(rug) > mem.trust_weighted_risk(poison)


def test_claimed_method_cannot_dominate_even_at_full_confidence():
    # B-1: provenance.method gates influence — a forged `claimed` edge at conf=1.0
    # must not score like a genuine first-party finding.
    mem = ForensicMemory(InMemoryRepository())
    claimed = [_edge("RUGGED", "w", "t", "2026-02-01", conf=1.0,
                     source="claimed:dust", method="claimed")]
    assert mem.trust_weighted_risk(claimed) < 0.3  # cannot even reach MEDIUM


def test_claimed_at_any_scale_never_reaches_medium():
    # B-2 (real): no number of forged `claimed` rugs — across many distinct tokens
    # AND many forged sources — can reach even MEDIUM. `claimed` is context-only:
    # it is stored and recalled but contributes zero risk magnitude.
    mem = ForensicMemory(InMemoryRepository())
    flood = [
        _edge("RUGGED", "w", f"fake{i}", "2026-02-01", conf=1.0,
              source=f"bot{i}", method="claimed")
        for i in range(50)
    ]
    assert mem.trust_weighted_risk(flood) < 0.3  # cannot reach MEDIUM at any scale


def test_sybil_source_strings_cannot_swing_the_verdict():
    # The core poisoning defense: an edge-writer who forges many distinct `source`
    # strings to fake "independent corroboration" must not move the score at all.
    # v3 ignores source strings entirely — a sybil spray scores identically to a
    # single source, and (being claimed) stays LOW.
    mem = ForensicMemory(InMemoryRepository())
    sybil = [
        _edge("RUGGED", "w", f"t{i}", "2026-02-01", conf=1.0,
              source=f"sybil-{i}", method="claimed")
        for i in range(8)
    ]
    single = [
        _edge("RUGGED", "w", f"t{i}", "2026-02-01", conf=1.0,
              source="one-source", method="claimed")
        for i in range(8)
    ]
    assert mem.trust_weighted_risk(sybil) == mem.trust_weighted_risk(single)
    assert mem.trust_weighted_risk(sybil) < 0.3  # forged sources cannot reach MEDIUM


def test_first_party_multiplicity_single_source_reaches_high():
    # The real serial-rugger signal: >=2 distinct first-party rugged tokens reach
    # HIGH even when observed via the SAME source — proving distinct-token
    # multiplicity (not source corroboration) is what drives the verdict.
    mem = ForensicMemory(InMemoryRepository())
    genuine = [_edge("RUGGED", "w", "tokA", "2026-02-01", source="helius:getAsset"),
               _edge("RUGGED", "w", "tokB", "2026-02-02", source="helius:getAsset")]
    assert mem.trust_weighted_risk(genuine) >= 0.6


def test_derived_at_any_scale_never_reaches_high():
    # `derived` (the agent's own inference) can corroborate up to MEDIUM but, lacking
    # a first-party on-chain observation, must never reach HIGH at any scale.
    mem = ForensicMemory(InMemoryRepository())
    flood = [
        _edge("RUGGED", "w", f"d{i}", "2026-02-01", conf=1.0,
              source=f"infer{i}", method="derived")
        for i in range(20)
    ]
    r = mem.trust_weighted_risk(flood)
    assert 0.3 <= r < 0.6  # reaches MEDIUM but is ceiling-capped below HIGH


def test_low_trust_reassertion_cannot_suppress_genuine_rug():
    # B-3: a later low-trust claim must not bury a genuine high-trust belief — the
    # genuine edge must still drive the score AND survive (unsuperseded) in recall.
    mem = ForensicMemory(InMemoryRepository())
    mem.remember([_edge("RUGGED", "rugZ", "tokA", "2026-02-01")], now="2026-02-01")
    mem.remember([_edge("RUGGED", "rugZ", "tokA", "2026-03-01", conf=0.05,
                        source="claimed:dust", method="claimed")], now="2026-03-01")
    hist = mem.recall_deployer_history("rugZ")
    genuine = [e for e in hist if e.provenance.method == "first_party"]
    assert len(genuine) == 1 and genuine[0].superseded_at is None  # genuine survives
    assert mem.trust_weighted_risk(hist) >= 0.3  # and still drives the score


def test_corroborating_source_for_same_fact_survives_in_recall(repo):
    # Two independent first-party observations of the SAME (type, dst) recorded in
    # separate remember() calls are CORROBORATION, not revision — equal trust from
    # DIFFERENT sources must not collapse one into the other; both survive.
    mem = ForensicMemory(repo)
    mem.remember([_edge("RUGGED", "w", "t", "2026-02-01", source="helius:getAsset")],
                 now="2026-02-01")
    mem.remember([_edge("RUGGED", "w", "t", "2026-02-02", source="rpc:largestAccounts")],
                 now="2026-02-02")
    live = [e for e in mem.recall("w") if e.superseded_at is None]
    assert len(live) == 2


def test_unknown_method_raises_on_scoring():
    # A typo'd method ('first-party' with a hyphen) must fail loudly, not silently
    # score as the lowest tier and nuke genuine first-party evidence.
    mem = ForensicMemory(InMemoryRepository())
    bad = [_edge("RUGGED", "w", "t", "2026-02-01", method="first-party")]
    with pytest.raises(ValueError):
        mem.trust_weighted_risk(bad)


def test_unknown_method_raises_on_remember():
    mem = ForensicMemory(InMemoryRepository())
    bad = [_edge("RUGGED", "w", "t", "2026-02-01", method="claimd")]
    with pytest.raises(ValueError):
        mem.remember(bad, now="2026-02-01")


def test_negative_confidence_cannot_lower_risk():
    # `confidence` is a forgeable float; a negative value must not invert the
    # noisy-OR and DRAG DOWN a genuine HIGH history — confidence is clamped to [0,1].
    mem = ForensicMemory(InMemoryRepository())
    genuine = [_edge("RUGGED", "w", "tA", "2026-02-01"),
               _edge("RUGGED", "w", "tB", "2026-02-02")]  # two first-party rugs -> HIGH
    poisoned = genuine + [_edge("RUGGED", "w", "tC", "2026-02-03", conf=-1.0)]
    assert mem.trust_weighted_risk(genuine) >= 0.6
    assert mem.trust_weighted_risk(poisoned) >= mem.trust_weighted_risk(genuine)


def test_higher_confidence_claim_cannot_supersede_first_party():
    # method-rank dominates supersession: a forged `claimed` re-assertion — even at
    # conf=1.0 (out-trusting a low-confidence genuine read) and replaying its source
    # string — can never retire a first-party belief.
    mem = ForensicMemory(InMemoryRepository())
    mem.remember([_edge("RUGGED", "w", "t", "2026-02-01", conf=0.05)], now="2026-02-01")
    mem.remember([_edge("RUGGED", "w", "t", "2026-02-02", conf=1.0,
                        source="helius:getAsset", method="claimed")], now="2026-02-02")
    hist = mem.recall_deployer_history("w")
    genuine = [e for e in hist if e.provenance.method == "first_party"]
    assert len(genuine) == 1 and genuine[0].superseded_at is None  # first-party survives


def test_first_party_plus_derived_flood_cannot_reach_high():
    # A single genuine first-party rug plus a flood of planted `derived` edges on
    # distinct tokens must NOT reach HIGH — `derived` cannot borrow the first-party
    # ceiling to manufacture a HIGH verdict off one real finding.
    mem = ForensicMemory(InMemoryRepository())
    edges = [_edge("RUGGED", "w", "real", "2026-02-01")]  # one genuine first-party rug
    edges += [
        _edge("RUGGED", "w", f"inf{i}", "2026-02-01", conf=1.0,
              source=f"s{i}", method="derived")
        for i in range(20)
    ]
    assert mem.trust_weighted_risk(edges) < 0.6  # stays below HIGH despite the flood


def test_method_tie_scoring_is_order_independent():
    # A fact carrying both a first-party and an equal-trust `derived` edge must score
    # identically regardless of edge order (no ceiling flip from backend iteration
    # order): the fact is first-party-tier because a first-party observation exists.
    mem = ForensicMemory(InMemoryRepository())
    edges = []
    for tok in ("tA", "tB", "tC"):
        edges.append(_edge("RUGGED", "w", tok, "2026-02-01", conf=0.6))  # first_party trust 0.6
        edges.append(_edge("RUGGED", "w", tok, "2026-02-01", conf=1.0,
                           source="x", method="derived"))  # derived trust 0.6
    assert mem.trust_weighted_risk(edges) == mem.trust_weighted_risk(list(reversed(edges)))
    assert mem.trust_weighted_risk(edges) >= 0.6  # three first-party-tier rugs -> HIGH
