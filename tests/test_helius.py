import httpx
import pytest
import respx

from anamnesis.forensic.helius import (
    HeliusClient,
    HeliusError,
    parse_authorities,
    top_holder_pct,
)

HELIUS_URL = "https://mainnet.helius-rpc.com/?api-key=test-key"


def _client() -> HeliusClient:
    return HeliusClient("test-key")


@respx.mock
def test_get_asset_returns_result_payload():
    respx.post(HELIUS_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": "anamnesis",
                "result": {"id": "mintA", "token_info": {"supply": 100, "decimals": 6}},
            },
        )
    )
    with _client() as client:
        asset = client.get_asset("mintA")
    assert asset["id"] == "mintA"
    assert asset["token_info"]["supply"] == 100


@respx.mock
def test_get_token_largest_accounts_returns_value_list():
    respx.post(HELIUS_URL).mock(
        return_value=httpx.Response(
            200,
            json={"result": {"value": [
                {"address": "acc1", "amount": "250"},
                {"address": "acc2", "amount": "100"},
            ]}},
        )
    )
    with _client() as client:
        accounts = client.get_token_largest_accounts("mintA")
    assert [a["address"] for a in accounts] == ["acc1", "acc2"]


@respx.mock
def test_rpc_error_raises_heliuserror():
    respx.post(HELIUS_URL).mock(
        return_value=httpx.Response(
            200, json={"error": {"code": -32000, "message": "boom"}}
        )
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
