from anamnesis.memory.graph import ForensicMemory
from anamnesis.memory.models import Edge, Provenance, make_edge_id
from anamnesis.memory.repository import InMemoryRepository


def _edge(type, src, dst, rec, conf=0.95, source="helius:getAsset") -> Edge:
    return Edge(
        make_edge_id(type, src, dst, rec), type, src, dst,
        rec, None, rec, None, Provenance(source, "first_party", conf),
    )


def test_repeat_deployer_history_is_recalled():
    mem = ForensicMemory(InMemoryRepository())
    mem.remember(
        [_edge("DEPLOYED", "ruggER", "tok1", "2026-02-01"),
         _edge("RUGGED", "ruggER", "tok1", "2026-02-09")],
        now="2026-02-09",
    )
    hist = mem.recall_deployer_history("ruggER")
    assert {e.type for e in hist} == {"DEPLOYED", "RUGGED"}


def test_trust_weighted_risk_rewards_corroboration():
    mem = ForensicMemory(InMemoryRepository())
    one = [_edge("RUGGED", "w", "t", "2026-02-01", source="helius:getAsset")]
    many = one + [
        _edge("RUGGED", "w", "t", "2026-02-01", source="rpc:largestAccounts"),
        _edge("RUGGED", "w", "t", "2026-02-01", source="enhanced:tx"),
    ]
    assert mem.trust_weighted_risk(many) > mem.trust_weighted_risk(one)


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
