"""Agent native-tool handlers — the pure, qwen-agent-free core of A.7.

These exercise the tool LOGIC (write-path provenance discipline, recall serialization,
the memory-driven assess_risk composition) without the LLM or qwen-agent, so the
poisoning-defense boundary the tools enforce is proven in plain CI. The thin
``@register_tool`` wrappers that adapt these to Qwen-Agent are validated at agent
assembly (A.9), where qwen-agent is installed.
"""
from anamnesis.agent.prompts import SYSTEM_INSTRUCTION
from anamnesis.agent.tools import assess_risk_handler, recall_handler, remember_handler
from anamnesis.forensic.signals import TokenProfile
from anamnesis.memory.graph import ForensicMemory
from anamnesis.memory.models import Provenance, make_edge
from anamnesis.memory.repository import InMemoryRepository


def test_remember_downgrades_forged_first_party_to_claimed():
    # WRITE-PATH DISCIPLINE (the poisoning lever): a prompt-injected / manipulated model
    # that calls remember() asserting method="first_party" must NOT get a first-party
    # edge. The tool forces `claimed`, so planted "rugs" are context-only and can never
    # forge a HIGH verdict — only the agent's own grounded read stamps first-party.
    mem = ForensicMemory(InMemoryRepository())
    forged = [
        {"type": "RUGGED", "src": "victim", "dst": f"tok{i}",
         "method": "first_party", "confidence": 1.0, "source": f"inject{i}"}
        for i in range(5)
    ]
    remember_handler(mem, forged, now="2026-02-01")
    stored = mem.recall("victim")
    assert stored and all(e.provenance.method == "claimed" for e in stored)
    # claimed is context-only -> these planted rugs cannot even reach MEDIUM
    assert mem.trust_weighted_risk(mem.recall_deployer_history("victim")) < 0.3


def test_remember_then_recall_roundtrips_the_claim():
    mem = ForensicMemory(InMemoryRepository())
    out = remember_handler(
        mem, [{"type": "SAME_CLUSTER", "src": "w", "dst": "scammer", "source": "user:tip"}],
        now="2026-02-01",
    )
    assert out["remembered"] == 1
    recalled = recall_handler(mem, "w")
    assert recalled["entity"] == "w"
    assert len(recalled["edges"]) == 1
    edge = recalled["edges"][0]
    assert edge["method"] == "claimed" and edge["type"] == "SAME_CLUSTER"


def test_assess_risk_flags_fresh_token_from_remembered_rugger_high():
    # The compounding-memory payoff at the tool layer: a fresh, clean-looking token from a
    # deployer with two REMEMBERED first-party rugs is flagged HIGH on memory alone.
    mem = ForensicMemory(InMemoryRepository())
    mem.remember(
        [make_edge("RUGGED", "ruggerX", "tokA", valid_from="2026-01-01",
                   recorded_at="2026-01-01",
                   provenance=Provenance("helius:getAsset", "first_party", 0.95)),
         make_edge("RUGGED", "ruggerX", "tokB", valid_from="2026-01-05",
                   recorded_at="2026-01-05",
                   provenance=Provenance("helius:getAsset", "first_party", 0.95))],
        now="2026-01-05",
    )
    clean = TokenProfile(mint="tokFresh", deployer="ruggerX", mint_authority=None,
                         freeze_authority=None, lp_secured=True, top_holder_pct=2.0,
                         holder_count=300)
    out = assess_risk_handler(mem, lambda mint: clean, "tokFresh")
    assert out["level"] == "high"
    assert out["remembered"]  # cites the remembered rug history


def test_assess_risk_unknown_deployer_is_low():
    mem = ForensicMemory(InMemoryRepository())
    clean = TokenProfile(mint="m", deployer="freshWallet", mint_authority=None,
                         freeze_authority=None, lp_secured=True, top_holder_pct=2.0,
                         holder_count=300)
    out = assess_risk_handler(mem, lambda mint: clean, "m")
    assert out["level"] == "low"


def test_system_instruction_is_memory_first():
    s = SYSTEM_INSTRUCTION.lower()
    assert "recall" in s                       # recall BEFORE judging
    assert "first_party" in s or "provenance" in s   # provenance-aware
    assert "fabricate" in s                    # never fabricate evidence
