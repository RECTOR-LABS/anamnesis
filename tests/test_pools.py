import httpx
import pytest
import respx

from anamnesis.forensic.pools import (
    AggregatorError,
    DexScreenerClient,
    PoolRef,
    discover_pools,
)

DEX_URL = "https://api.dexscreener.com/token-pairs/v1/solana/mintA"


class _FakeDex:
    def __init__(self, pairs):
        self._pairs = pairs

    def token_pairs(self, mint):
        return self._pairs


def test_discover_pools_maps_pairs_to_poolrefs():
    pairs = [
        {"pairAddress": "POOL1", "dexId": "raydium", "liquidity": {"usd": 42000.0}},
        {"pairAddress": "POOL2", "dexId": "meteora", "liquidity": {"usd": None}},
    ]
    refs = discover_pools(_FakeDex(pairs), "mintA")
    assert refs == [
        PoolRef(pool="POOL1", dex_id="raydium", liquidity_usd=42000.0),
        PoolRef(pool="POOL2", dex_id="meteora", liquidity_usd=None),
    ]


def test_discover_pools_skips_pairs_without_address():
    refs = discover_pools(_FakeDex([{"dexId": "raydium"}]), "mintA")
    assert refs == []


@respx.mock
def test_token_pairs_retries_on_429_then_succeeds():
    # DexScreener's keyless API is rate-limited; a 429 during high-pool fan-out must be retried
    # (with backoff), not collapse the whole LP verdict to UNKNOWN on the first throttle.
    respx.get(DEX_URL).mock(
        side_effect=[httpx.Response(429), httpx.Response(200, json=[{"pairAddress": "P1"}])]
    )
    with DexScreenerClient(max_retries=2) as dex:
        assert dex.token_pairs("mintA") == [{"pairAddress": "P1"}]


@respx.mock
def test_token_pairs_429_give_up_raises_aggregator_error():
    respx.get(DEX_URL).mock(return_value=httpx.Response(429, text="rate limited"))
    with DexScreenerClient(max_retries=0) as dex, pytest.raises(AggregatorError) as exc:
        dex.token_pairs("mintA")
    assert "429" in str(exc.value)
