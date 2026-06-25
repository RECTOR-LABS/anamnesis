"""Agent native-tool handlers — the pure, qwen-agent-free core of A.7.

These exercise the tool LOGIC (write-path provenance discipline, recall serialization,
the memory-driven assess_risk composition) without the LLM or qwen-agent, so the
poisoning-defense boundary the tools enforce is proven in plain CI. The thin
``@register_tool`` wrappers that adapt these to Qwen-Agent are validated at agent
assembly (A.9), where qwen-agent is installed.
"""
from anamnesis.agent.prompts import SYSTEM_INSTRUCTION
from anamnesis.agent.tools import assess_risk_handler, recall_handler, remember_handler
from anamnesis.forensic.signals import LpAssessment, LpStatus, TokenProfile
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


def test_remember_ignores_model_supplied_timestamps():
    # The model controls neither transaction time nor validity time — the agent stamps both
    # from its own clock. A malformed/garbage timestamp smuggled into a fact must not crash
    # the write or discard the rest of the batch; it is simply ignored.
    mem = ForensicMemory(InMemoryRepository())
    out = remember_handler(
        mem, [{"type": "SAME_CLUSTER", "src": "w", "dst": "x", "valid_from": "yesterday"}],
        now="2026-02-01",
    )
    assert out["remembered"] == 1
    [e] = mem.recall("w")
    assert e.valid_from == "2026-02-01T00:00:00.000000+00:00"  # agent's clock, not the model's


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
                         freeze_authority=None, lp=LpAssessment(LpStatus.SECURED), top_holder_pct=2.0,
                         holder_count=300)
    out = assess_risk_handler(mem, lambda mint: clean, "tokFresh")
    assert out["level"] == "high"
    assert out["remembered"]  # cites the remembered rug history


def test_assess_risk_unknown_deployer_is_low():
    mem = ForensicMemory(InMemoryRepository())
    clean = TokenProfile(mint="m", deployer="freshWallet", mint_authority=None,
                         freeze_authority=None, lp=LpAssessment(LpStatus.SECURED), top_holder_pct=2.0,
                         holder_count=300)
    out = assess_risk_handler(mem, lambda mint: clean, "m")
    assert out["level"] == "low"


def test_build_lp_aware_profile_wires_analyzer_into_verdict():
    # The agent's verdict path (assess_risk) must run the REAL on-chain LP analyzer, not the
    # UNKNOWN default — otherwise a withdrawable-LP rug only ever emits the low LP_UNVERIFIED
    # signal and the high LP_NOT_SECURED can never reach the verdict (it was wired into the MCP
    # get_token_profile path only). A withdrawable Raydium pool must surface NOT_SECURED here.
    import json
    from pathlib import Path

    from anamnesis.agent.tools import build_lp_aware_profile

    fx = json.loads(
        (Path(__file__).parent / "fixtures" / "lp_pool_accounts.json").read_text()
    )["raydium_v4"]
    ray_v4 = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"

    class _Dex:
        def token_pairs(self, mint):
            return [{"pairAddress": fx["pool"], "dexId": "raydium", "liquidity": {"usd": 50_000.0}}]

    class _Helius:
        def get_asset(self, mint):
            return {"token_info": {"supply": "1000"}, "authorities": []}

        def get_token_largest_accounts(self, mint):
            return [{"address": "TA", "amount": "1"}]

        def get_token_accounts(self, mint, *, page=1, limit=1000):
            return {"total": 300}

        def oldest_signature(self, address, *, page_limit=1000):
            return None  # unresolved deployer -> falls back to (empty) update authority

        def get_account_info(self, addr, *, encoding="jsonParsed"):
            if addr == fx["pool"]:
                return {"data": [fx["data_b64"], "base64"]} if encoding == "base64" else {"owner": ray_v4}
            return {"data": {"parsed": {"info": {"owner": "deployerWallet"}}}}  # withdrawable

        def get_token_supply(self, mint):
            return 1000

    profile = build_lp_aware_profile(_Helius(), _Dex(), "mintW")
    assert profile.lp.status is LpStatus.NOT_SECURED  # analyzer ran (not the UNKNOWN default)

    mem = ForensicMemory(InMemoryRepository())
    out = assess_risk_handler(mem, lambda m: profile, "mintW")
    assert "LP_NOT_SECURED" in {s["code"] for s in out["signals"]}  # high LP signal reaches verdict


def test_system_instruction_is_memory_first():
    s = SYSTEM_INSTRUCTION.lower()
    assert "recall" in s                       # recall BEFORE judging
    assert "first_party" in s or "provenance" in s   # provenance-aware
    assert "fabricate" in s                    # never fabricate evidence
