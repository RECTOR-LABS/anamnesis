import httpx
import pytest
import respx

from anamnesis.forensic.helius import (
    HeliusClient,
    HeliusError,
    fee_payer,
    parse_authorities,
    resolve_deployer,
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


def test_fee_payer_extracts_first_account_jsonparsed():
    tx = {"transaction": {"message": {"accountKeys": [
        {"pubkey": "payer", "signer": True}, {"pubkey": "other"}]}}}
    assert fee_payer(tx) == "payer"


def test_fee_payer_handles_string_keys_and_missing():
    tx = {"transaction": {"message": {"accountKeys": ["payerStr", "x"]}}}
    assert fee_payer(tx) == "payerStr"
    assert fee_payer({}) is None
    assert fee_payer({"transaction": {"message": {"accountKeys": []}}}) is None


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
