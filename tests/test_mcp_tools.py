"""Unit tests for the A.8 forensic MCP tool handlers — pure over an injected client.

Mirrors test_helius.py's _FakeClient approach (order-independent canned reads) so the
multi-call composition + serialization are tested without network or the mcp package;
these run in CI. Raising fakes cover the error-mapping path.
"""
from __future__ import annotations

import httpx

from anamnesis.forensic.helius import HeliusError
from anamnesis.forensic.mcp_tools import (
    deployer_dict,
    deployer_token_history_dict,
    holders_dict,
    token_profile_dict,
    trace_funding_dict,
)
from anamnesis.forensic.signals import LpAssessment, LpEvidence, LpStatus


class _FakeClient:
    """Canned, order-independent forensic reads: active mint authority, one big holder."""

    def get_asset(self, mint: str) -> dict:
        return {
            "token_info": {"supply": 1000, "mint_authority": "deployerW", "freeze_authority": None},
            "authorities": [{"address": "deployerW", "scopes": ["full"]}],
        }

    def get_token_largest_accounts(self, mint: str) -> list[dict]:
        return [{"address": "acc1", "amount": "300"}, {"address": "acc2", "amount": "50"}]

    def oldest_signature(self, mint: str, **_: object) -> str | None:
        return "deploySig"

    def get_transaction(self, signature: str) -> dict:
        return {"blockTime": 1700000000,
                "transaction": {"message": {"accountKeys": [{"pubkey": "deployerW"}]}}}

    def get_token_accounts(self, mint: str, **_: object) -> dict:
        return {"total": 742}


def test_token_profile_dict_default_resolver_reports_unknown_lp():
    out = token_profile_dict(_FakeClient(), "mintA")
    assert out == {
        "mint": "mintA",
        "deployer": "deployerW",
        "created_at": "2023-11-14T22:13:20+00:00",
        "mint_authority": "deployerW",
        "freeze_authority": None,
        "lp": {"status": "unknown", "evidence": []},
        "top_holder_pct": 30.0,
        "holder_count": 742,
    }
    assert "lp_secured" not in out


def test_token_profile_dict_surfaces_injected_lp_evidence():
    out = token_profile_dict(
        _FakeClient(), "mintA",
        lp_resolver=lambda c, m: LpAssessment(LpStatus.SECURED, [
            LpEvidence("raydium_v4", "POOL", "LPMINT", "lp_mint_burned", True, "burned",
                       50_000.0, "LPMINT")]),
    )
    assert out["lp"]["status"] == "secured"
    assert out["lp"]["evidence"][0] == {
        "venue": "raydium_v4", "pool": "POOL", "lp_mint": "LPMINT", "method": "lp_mint_burned",
        "secured": True, "detail": "burned", "liquidity_usd": 50_000.0, "citation": "LPMINT"}


def test_deployer_dict_returns_deployer_and_created_at():
    out = deployer_dict(_FakeClient(), "mintA")
    assert out == {"mint": "mintA", "deployer": "deployerW",
                   "created_at": "2023-11-14T22:13:20+00:00"}


def test_holders_dict_reports_concentration_and_truncates():
    out = holders_dict(_FakeClient(), "mintA", top_n=1)
    assert out["mint"] == "mintA"
    assert out["holder_count"] == 742
    assert out["top_holder_pct"] == 30.0                       # 300 / 1000
    assert out["largest"] == [{"address": "acc1", "amount": "300"}]   # truncated to top_n=1


class _HeliusRaisingClient(_FakeClient):
    def get_asset(self, mint: str) -> dict:
        raise HeliusError("getAsset failed: boom")


class _HttpxRaisingClient(_FakeClient):
    def get_asset(self, mint: str) -> dict:
        raise httpx.HTTPError("network down")


def test_handlers_map_upstream_errors_to_structured_result():
    # token_profile_dict + holders_dict both open with get_asset -> clean degradation.
    assert token_profile_dict(_HeliusRaisingClient(), "mintA") == {
        "error": "getAsset failed: boom", "mint": "mintA"}
    assert holders_dict(_HeliusRaisingClient(), "mintA") == {
        "error": "getAsset failed: boom", "mint": "mintA"}
    assert token_profile_dict(_HttpxRaisingClient(), "mintA") == {
        "error": "network down", "mint": "mintA"}


# --- code-review hardening (fixes 1-4): malformed payloads, blank mint, top_n ----------


class _NullAssetClient(_FakeClient):
    # getAsset whose JSON `result` is null -> HeliusClient._rpc returns None.
    def get_asset(self, mint: str):
        return None


class _BadSupplyClient(_FakeClient):
    def get_asset(self, mint: str) -> dict:
        return {"token_info": {"supply": "n/a"}, "authorities": [{"address": "d", "scopes": ["full"]}]}


class _NonDictHoldersClient(_FakeClient):
    def get_token_largest_accounts(self, mint: str) -> list:
        return [None]  # malformed value entry (not a dict)


class _DeployerRpcErrorClient(_FakeClient):
    def oldest_signature(self, mint: str, **_: object):
        raise HeliusError("getSignaturesForAddress failed: 429")


def test_blank_mint_is_rejected_at_the_boundary():
    # mint validation on the public entry points (no wasted RPC, clear error).
    handlers = (token_profile_dict, deployer_dict, holders_dict,
                trace_funding_dict, deployer_token_history_dict)
    for handler in handlers:
        out = handler(_FakeClient(), "   ")
        assert "error" in out and out["mint"] == "   "
    assert "error" in token_profile_dict(_FakeClient(), "")


def test_handlers_degrade_on_malformed_payload():
    # A null getAsset result, a non-numeric supply, and a non-dict holder entry must each
    # degrade to {"error", "mint"} instead of crashing the stdio loop.
    assert "error" in token_profile_dict(_NullAssetClient(), "mintA")
    assert "error" in holders_dict(_NullAssetClient(), "mintA")
    assert "error" in holders_dict(_BadSupplyClient(), "mintA")
    assert "error" in holders_dict(_NonDictHoldersClient(), "mintA")


class _MegaCapLargestAccountsClient(_FakeClient):
    # Mega-cap mints (USDC/SOL/BONK) make getTokenLargestAccounts error, but getAsset +
    # getTokenAccounts still work — concentration should degrade to unknown, not fail the tool.
    def get_token_largest_accounts(self, mint: str) -> list[dict]:
        raise HeliusError("getTokenLargestAccounts failed: HTTP 400")


def test_holders_dict_degrades_concentration_on_mega_cap():
    # The getTokenLargestAccounts RPC errors on mega-caps; the tool must still return
    # holder_count with concentration marked unknown, not collapse to an {"error"} dict.
    out = holders_dict(_MegaCapLargestAccountsClient(), "mintA")
    assert "error" not in out
    assert out["holder_count"] == 742
    assert out["top_holder_pct"] is None
    assert out["largest"] == []


class _NullValueLargestClient(_FakeClient):
    # getTokenLargestAccounts whose RPC value is null -> helius returns None (not a list, no raise).
    def get_token_largest_accounts(self, mint: str):
        return None


def test_holders_dict_degrades_when_largest_accounts_is_null():
    # A null getTokenLargestAccounts value (helius returns None, no exception) degrades
    # concentration to unknown — same partial-result contract as the mega-cap RPC-error path.
    out = holders_dict(_NullValueLargestClient(), "mintA")
    assert "error" not in out
    assert out["holder_count"] == 742
    assert out["top_holder_pct"] is None
    assert out["largest"] == []


def test_deployer_dict_degrades_on_rpc_error():
    # The previously-untested deployer_dict error branch: an RPC error on its primary read
    # (oldest_signature) degrades, it does not bubble out of the stdio loop.
    assert deployer_dict(_DeployerRpcErrorClient(), "mintA") == {
        "error": "getSignaturesForAddress failed: 429", "mint": "mintA"}


def test_holders_dict_clamps_nonpositive_top_n():
    # A negative top_n must NOT silently slice from the wrong end (dropping the top holder);
    # it clamps to an empty list rather than returning a misleading subset.
    assert holders_dict(_FakeClient(), "mintA", top_n=-1)["largest"] == []
    assert holders_dict(_FakeClient(), "mintA", top_n=0)["largest"] == []


# --- A.8b: trace_funding handler ----------------------------------------------------------


class _FundingClient:
    # mint creation tx -> deployer "depl"; deployer's earliest tx -> funder "cexHot"
    def oldest_signature(self, address, **_):
        return {"mintA": "createSig", "depl": "fundSig"}.get(address)

    def get_transaction(self, signature):
        payer = {"createSig": "depl", "fundSig": "cexHot"}[signature]
        return {"blockTime": 1700000000,
                "transaction": {"message": {"accountKeys": [{"pubkey": payer}]}}}

    def get_asset(self, mint):  # resolve_origin fallback (unused once the sig resolves)
        return {"authorities": []}


def test_trace_funding_dict_classifies_known_funder(monkeypatch):
    monkeypatch.setattr("anamnesis.forensic.helius.FUNDING_SOURCES", {"cexHot": "cex"})
    out = trace_funding_dict(_FundingClient(), "mintA")
    assert out == {"mint": "mintA", "deployer": "depl", "funder": "cexHot",
                   "source_type": "cex", "funded_at": "2023-11-14T22:13:20+00:00"}


def test_trace_funding_dict_unknown_when_self_funded():
    out = trace_funding_dict(_FakeClient(), "mintA")
    assert out == {"mint": "mintA", "deployer": "deployerW", "funder": None,
                   "source_type": "unknown", "funded_at": None}


def test_trace_funding_dict_degrades_on_rpc_error():
    assert trace_funding_dict(_DeployerRpcErrorClient(), "mintA") == {
        "error": "getSignaturesForAddress failed: 429", "mint": "mintA"}


# --- A.8b: deployer_token_history handler -------------------------------------------------


class _DeployerHistoryClient(_FakeClient):
    # mint creation -> deployer "depl"; deployer history page -> one creating tx (h1)
    def oldest_signature(self, address, **_):
        return {"mintA": "createSig", "depl": "h1"}.get(address, "createSig")

    def get_signatures_for_address(self, address, *, before=None, limit=1000):
        return [] if before else [{"signature": "h1"}, {"signature": "h2"}]

    def get_transaction(self, signature):
        if signature == "createSig":
            return {"blockTime": 1700000000,
                    "transaction": {"message": {"accountKeys": [{"pubkey": "depl"}]}}}
        mint = {"h1": "childMintA"}.get(signature)
        ix = [{"parsed": {"type": "initializeMint", "info": {"mint": mint}}}] if mint else []
        return {"blockTime": 1700000000, "transaction": {"message": {"instructions": ix}}}


def test_deployer_token_history_dict_lists_created_mints():
    out = deployer_token_history_dict(_DeployerHistoryClient(), "mintA")
    assert out == {
        "mint": "mintA",
        "deployer": "depl",
        "created_mints": [{"mint": "childMintA", "created_at": "2023-11-14T22:13:20+00:00"}],
        "count": 1,
        "truncated": False,
    }


def test_deployer_token_history_dict_degrades_on_rpc_error():
    assert deployer_token_history_dict(_DeployerRpcErrorClient(), "mintA") == {
        "error": "getSignaturesForAddress failed: 429", "mint": "mintA"}
