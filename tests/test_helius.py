import httpx
import pytest
import respx

from anamnesis.forensic.helius import (
    HeliusClient,
    HeliusError,
    build_token_profile,
    classify_funder,
    creation_time,
    fee_payer,
    holder_count,
    parse_authorities,
    resolve_deployer,
    resolve_origin,
    top_holder_pct,
    update_authority,
)

HELIUS_URL = "https://mainnet.helius-rpc.com/?api-key=test-key"


def _client() -> HeliusClient:
    return HeliusClient("test-key")


def _json(payload: dict) -> httpx.Response:
    return httpx.Response(200, json=payload)


@respx.mock
def test_get_asset_returns_result_payload():
    respx.post(HELIUS_URL).mock(
        return_value=_json(
            {
                "jsonrpc": "2.0",
                "id": "anamnesis",
                "result": {"id": "mintA", "token_info": {"supply": 100, "decimals": 6}},
            }
        )
    )
    with _client() as client:
        asset = client.get_asset("mintA")
    assert asset["id"] == "mintA"
    assert asset["token_info"]["supply"] == 100


@respx.mock
def test_get_token_largest_accounts_returns_value_list():
    respx.post(HELIUS_URL).mock(
        return_value=_json(
            {"result": {"value": [
                {"address": "acc1", "amount": "250"},
                {"address": "acc2", "amount": "100"},
            ]}}
        )
    )
    with _client() as client:
        accounts = client.get_token_largest_accounts("mintA")
    assert [a["address"] for a in accounts] == ["acc1", "acc2"]


@respx.mock
def test_rpc_error_raises_heliuserror():
    respx.post(HELIUS_URL).mock(
        return_value=_json({"error": {"code": -32000, "message": "boom"}})
    )
    with _client() as client, pytest.raises(HeliusError, match="getAsset"):
        client.get_asset("mintA")


@respx.mock
def test_rpc_missing_result_raises_heliuserror():
    # A well-formed envelope carrying neither result nor error is a protocol
    # violation — surface it as HeliusError, not a bare KeyError.
    respx.post(HELIUS_URL).mock(return_value=_json({"jsonrpc": "2.0", "id": "anamnesis"}))
    with _client() as client, pytest.raises(HeliusError, match="getAsset"):
        client.get_asset("mintA")


@respx.mock
def test_get_token_largest_accounts_tolerates_null_result():
    # ``result: null`` (e.g. nothing indexed yet) must degrade to "no holders",
    # not crash on ``None.get``.
    respx.post(HELIUS_URL).mock(return_value=_json({"result": None}))
    with _client() as client:
        assert client.get_token_largest_accounts("mintA") == []


def test_parse_authorities_absent_means_renounced():
    asset = {"token_info": {"supply": 100, "decimals": 6}}
    assert parse_authorities(asset) == (None, None)


def test_parse_authorities_active_returns_addresses():
    asset = {"token_info": {"mint_authority": "w", "freeze_authority": "w"}}
    assert parse_authorities(asset) == ("w", "w")


def test_top_holder_pct_computes_largest_over_supply():
    largest = [{"address": "a", "amount": "250"}, {"address": "b", "amount": "100"}]
    assert top_holder_pct(largest, supply=1000) == 25.0


def test_top_holder_pct_zero_supply_or_no_accounts_is_safe():
    assert top_holder_pct([{"address": "a", "amount": "250"}], supply=0) == 0.0
    assert top_holder_pct([], supply=1000) == 0.0


def test_top_holder_pct_malformed_amount_is_safe():
    # A missing or non-numeric ``amount`` on the top account must not abort the
    # whole profile build — treat unknown concentration as 0.0 (safe).
    assert top_holder_pct([{"address": "a"}], supply=1000) == 0.0
    assert top_holder_pct([{"address": "a", "amount": "n/a"}], supply=1000) == 0.0


@respx.mock
def test_get_signatures_for_address_returns_list():
    respx.post(HELIUS_URL).mock(return_value=_json({"result": [{"signature": "sigX"}]}))
    with _client() as client:
        sigs = client.get_signatures_for_address("addr")
    assert sigs == [{"signature": "sigX"}]


@respx.mock
def test_get_transaction_returns_payload():
    respx.post(HELIUS_URL).mock(
        return_value=_json({"result": {"blockTime": 123, "transaction": {"message": {}}}})
    )
    with _client() as client:
        tx = client.get_transaction("sig")
    assert tx["blockTime"] == 123


@respx.mock
def test_oldest_signature_paginates_to_oldest():
    # Newest-first pages; the oldest signature is the last item of the final page.
    respx.post(HELIUS_URL).mock(
        side_effect=[
            _json({"result": [{"signature": "s3"}, {"signature": "s2"}]}),
            _json({"result": [{"signature": "s1"}]}),
        ]
    )
    with _client() as client:
        assert client.oldest_signature("addr", page_limit=2) == "s1"


@respx.mock
def test_oldest_signature_tolerates_entry_without_signature():
    # A malformed oldest entry (no "signature") must stop pagination cleanly
    # rather than raise KeyError.
    respx.post(HELIUS_URL).mock(
        return_value=_json({"result": [{"signature": "s2"}, {"err": "no-sig"}]})
    )
    with _client() as client:
        assert client.oldest_signature("addr", page_limit=2) is None


@respx.mock
def test_get_token_accounts_returns_total():
    respx.post(HELIUS_URL).mock(
        return_value=_json({"result": {"total": 1234, "token_accounts": []}})
    )
    with _client() as client:
        result = client.get_token_accounts("mintA")
    assert result["total"] == 1234


@respx.mock
def test_holder_count_reads_total():
    respx.post(HELIUS_URL).mock(return_value=_json({"result": {"total": 1234}}))
    with _client() as client:
        assert holder_count(client, "mintA") == 1234


@respx.mock
def test_holder_count_tolerates_null_result():
    # ``result: null`` must read as zero holders, not crash on ``None.get``.
    respx.post(HELIUS_URL).mock(return_value=_json({"result": None}))
    with _client() as client:
        assert holder_count(client, "mintA") == 0


def test_fee_payer_extracts_first_account_jsonparsed():
    tx = {"transaction": {"message": {"accountKeys": [
        {"pubkey": "payer", "signer": True}, {"pubkey": "other"}]}}}
    assert fee_payer(tx) == "payer"


def test_fee_payer_handles_string_keys_and_missing():
    tx = {"transaction": {"message": {"accountKeys": ["payerStr", "x"]}}}
    assert fee_payer(tx) == "payerStr"
    assert fee_payer({}) is None
    assert fee_payer({"transaction": {"message": {"accountKeys": []}}}) is None


def test_creation_time_from_block_time():
    assert creation_time({"blockTime": 1700000000}) == "2023-11-14T22:13:20+00:00"
    assert creation_time({}) is None


def test_update_authority_prefers_full_scope():
    asset = {"authorities": [
        {"address": "u1", "scopes": ["metadata"]},
        {"address": "u2", "scopes": ["full"]}]}
    assert update_authority(asset) == "u2"


def test_update_authority_absent_returns_none():
    assert update_authority({"authorities": []}) is None
    assert update_authority({}) is None


@respx.mock
def test_resolve_deployer_uses_creation_tx_fee_payer():
    respx.post(HELIUS_URL).mock(
        side_effect=[
            _json({"result": [{"signature": "deploySig"}]}),
            _json({"result": {"transaction": {"message": {"accountKeys": [
                {"pubkey": "deployerW"}]}}}}),
        ]
    )
    with _client() as client:
        assert resolve_deployer(client, "mintA") == "deployerW"


@respx.mock
def test_resolve_deployer_falls_back_to_update_authority():
    # No signatures -> creation tx unresolvable -> fall back to update authority.
    respx.post(HELIUS_URL).mock(
        side_effect=[
            _json({"result": []}),
            _json({"result": {"authorities": [{"address": "updAuth", "scopes": ["full"]}]}}),
        ]
    )
    with _client() as client:
        assert resolve_deployer(client, "mintA") == "updAuth"


@respx.mock
def test_resolve_origin_returns_deployer_and_created_at():
    respx.post(HELIUS_URL).mock(
        side_effect=[
            _json({"result": [{"signature": "deploySig"}]}),
            _json({"result": {"blockTime": 1700000000, "transaction": {"message": {
                "accountKeys": [{"pubkey": "deployerW"}]}}}}),
        ]
    )
    with _client() as client:
        assert resolve_origin(client, "mintA") == ("deployerW", "2023-11-14T22:13:20+00:00")


@respx.mock
def test_resolve_origin_fallback_has_no_created_at():
    respx.post(HELIUS_URL).mock(
        side_effect=[
            _json({"result": []}),
            _json({"result": {"authorities": [{"address": "updAuth", "scopes": ["full"]}]}}),
        ]
    )
    with _client() as client:
        assert resolve_origin(client, "mintA") == ("updAuth", None)


@respx.mock
def test_resolve_origin_denylists_launchpad_update_authority():
    # B-4: when the creation tx is unresolvable, the update-authority fallback must NOT
    # collapse a launchpad token onto a shared program PDA — that re-introduces the exact
    # false-clustering the fee-payer design avoids. A denylisted launchpad authority
    # resolves to None (unknown deployer), not a bogus shared cluster key.
    from anamnesis.forensic.helius import LAUNCHPAD_AUTHORITIES

    pda = next(iter(LAUNCHPAD_AUTHORITIES))
    respx.post(HELIUS_URL).mock(
        side_effect=[
            _json({"result": []}),
            _json({"result": {"authorities": [{"address": pda, "scopes": ["full"]}]}}),
        ]
    )
    with _client() as client:
        assert resolve_origin(client, "mintA") == (None, None)


class _FakeClient:
    """Order-independent stand-in for HeliusClient — canned forensic reads."""

    def get_asset(self, mint: str) -> dict:
        return {
            "token_info": {
                "supply": 1000,
                "mint_authority": "deployerW",
                "freeze_authority": None,
            },
            "authorities": [{"address": "deployerW", "scopes": ["full"]}],
        }

    def get_token_largest_accounts(self, mint: str) -> list[dict]:
        return [{"address": "acc1", "amount": "300"}]

    def oldest_signature(self, mint: str, **_: object) -> str | None:
        return "deploySig"

    def get_transaction(self, signature: str) -> dict:
        return {
            "blockTime": 1700000000,
            "transaction": {"message": {"accountKeys": [{"pubkey": "deployerW"}]}},
        }

    def get_token_accounts(self, mint: str, **_: object) -> dict:
        return {"total": 742}


def test_build_token_profile_assembles_all_fields():
    profile = build_token_profile(_FakeClient(), "mintA")
    assert profile.mint == "mintA"
    assert profile.deployer == "deployerW"            # creation-tx fee payer
    assert profile.mint_authority == "deployerW"
    assert profile.freeze_authority is None
    assert profile.top_holder_pct == 30.0             # 300 / 1000
    assert profile.holder_count == 742
    assert profile.created_at == "2023-11-14T22:13:20+00:00"
    assert profile.lp_secured is False                # conservative default


def test_build_token_profile_uses_injected_lp_resolver():
    profile = build_token_profile(_FakeClient(), "mintA", lp_resolver=lambda c, m: True)
    assert profile.lp_secured is True


class _NoDeployerClient(_FakeClient):
    def oldest_signature(self, mint: str, **_: object) -> str | None:
        return None

    def get_asset(self, mint: str) -> dict:
        return {"token_info": {"supply": 1000}, "authorities": []}


def test_build_token_profile_allows_unknown_deployer():
    profile = build_token_profile(_NoDeployerClient(), "mintA")
    assert profile.deployer is None


# --- A.8b: funding-source classification --------------------------------------------------


def test_classify_funder_categorizes_known_and_unknown(monkeypatch):
    monkeypatch.setattr(
        "anamnesis.forensic.helius.FUNDING_SOURCES",
        {"cexAddr": "cex", "bridgeAddr": "bridge", "mixerAddr": "mixer"},
    )
    assert classify_funder("cexAddr") == "cex"
    assert classify_funder("bridgeAddr") == "bridge"
    assert classify_funder("mixerAddr") == "mixer"
    assert classify_funder("randomAddr") == "unknown"
    assert classify_funder(None) == "unknown"
