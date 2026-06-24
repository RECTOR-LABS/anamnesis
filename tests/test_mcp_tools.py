"""Unit tests for the A.8 forensic MCP tool handlers — pure over an injected client.

Mirrors test_helius.py's _FakeClient approach (order-independent canned reads) so the
multi-call composition + serialization are tested without network or the mcp package;
these run in CI. Raising fakes cover the error-mapping path.
"""
from __future__ import annotations

import httpx

from anamnesis.forensic.helius import HeliusError
from anamnesis.forensic.mcp_tools import deployer_dict, holders_dict, token_profile_dict


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


def test_token_profile_dict_serializes_all_fields():
    out = token_profile_dict(_FakeClient(), "mintA")
    assert out == {
        "mint": "mintA",
        "deployer": "deployerW",
        "created_at": "2023-11-14T22:13:20+00:00",
        "mint_authority": "deployerW",
        "freeze_authority": None,
        "lp_secured": False,
        "top_holder_pct": 30.0,
        "holder_count": 742,
    }


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
