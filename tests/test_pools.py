from anamnesis.forensic.pools import PoolRef, discover_pools


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
