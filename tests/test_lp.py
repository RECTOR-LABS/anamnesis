import base64
import json
from pathlib import Path

from anamnesis.forensic.lp import (
    INCINERATOR,
    LP_LOCKERS,
    RAYDIUM_CPMM_LP_MINT_OFFSET,
    RAYDIUM_V4_LP_MINT_OFFSET,
    LpAnalyzer,
    _b58encode,
    _pubkey_at,
    aggregate,
    largest_holders_with_owners,
    secured_fraction,
    venue_of,
    verify_fungible,
)
from anamnesis.forensic.pools import AggregatorError, PoolRef
from anamnesis.forensic.signals import LpEvidence, LpStatus

_FX = json.loads((Path(__file__).parent / "fixtures" / "lp_pool_accounts.json").read_text())


def _burned_client(fx):
    """Fake Helius: returns the real pool account for fx['pool']; every LP holder = incinerator."""
    class _C:
        def get_account_info(self, addr, *, encoding="jsonParsed"):
            if addr == fx["pool"]:
                return {"data": [fx["data_b64"], "base64"]}
            return {"data": {"parsed": {"info": {"owner": INCINERATOR}}}}

        def get_token_supply(self, mint):
            return 1000

        def get_token_largest_accounts(self, mint):
            return [{"address": "TA", "amount": "1000"}]

    return _C()

_LOCKER = next(iter(LP_LOCKERS))  # a curated locker program id


def _ev(secured, usd, venue="raydium_v4"):
    return LpEvidence(
        venue=venue, pool="P", lp_mint="L", method="m", secured=secured, detail="d", liquidity_usd=usd,
    )


def test_secured_fraction_counts_incinerator_and_locker_held():
    holders = [
        {"owner": INCINERATOR, "amount": "600"},
        {"owner": _LOCKER, "amount": "350"},
        {"owner": "someDeployer", "amount": "50"},
    ]
    assert secured_fraction(holders, supply=1000) == 0.95


def test_secured_fraction_zero_when_all_withdrawable():
    assert secured_fraction([{"owner": "deployer", "amount": "1000"}], 1000) == 0.0


def test_secured_fraction_zero_supply_is_zero_not_crash():
    assert secured_fraction([{"owner": INCINERATOR, "amount": "0"}], 0) == 0.0


def test_aggregate_empty_is_unknown():
    assert aggregate([]) is LpStatus.UNKNOWN


def test_aggregate_nondust_unsecured_dominates():
    assert aggregate([_ev(True, 50_000), _ev(False, 20_000)]) is LpStatus.NOT_SECURED


def test_aggregate_dust_unsecured_does_not_drive_verdict():
    # a $50 decoy "unsecured" pool must not override a deep secured pool
    assert aggregate([_ev(True, 80_000), _ev(False, 50)]) is LpStatus.SECURED


def test_aggregate_unknown_when_only_dust_pools():
    assert aggregate([_ev(True, 50), _ev(True, 10)]) is LpStatus.UNKNOWN


def test_aggregate_unknown_when_nondust_has_none():
    assert aggregate([_ev(True, 50_000), _ev(None, 30_000)]) is LpStatus.UNKNOWN


def test_aggregate_secured_when_all_nondust_secured():
    assert aggregate([_ev(True, 50_000), _ev(True, 30_000)]) is LpStatus.SECURED


class _AcctClient:
    """Fake Helius exposing get_account_info / get_token_largest_accounts (addr -> value dict)."""

    def __init__(self, accounts, largest=None):
        self._accounts = accounts
        self._largest = largest or []

    def get_account_info(self, addr, *, encoding="jsonParsed"):
        return self._accounts.get(addr, {})

    def get_token_largest_accounts(self, mint):
        return self._largest


def test_venue_of_routes_by_owning_program():
    ray_v4 = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
    assert venue_of(_AcctClient({"POOL": {"owner": ray_v4}}), "POOL") == "raydium_v4"


def test_venue_of_unknown_program_is_unknown():
    assert venue_of(_AcctClient({"POOL": {"owner": "SomeOtherProgram"}}), "POOL") == "unknown"


def test_largest_holders_with_owners_resolves_each_owner():
    c = _AcctClient(
        accounts={
            "TA1": {"data": {"parsed": {"info": {"owner": "incin"}}}},
            "TA2": {"data": {"parsed": {"info": {"owner": "deployer"}}}},
        },
        largest=[{"address": "TA1", "amount": "600"}, {"address": "TA2", "amount": "400"}],
    )
    holders = largest_holders_with_owners(c, "lpMint")
    assert holders == [{"owner": "incin", "amount": "600"}, {"owner": "deployer", "amount": "400"}]


def test_b58encode_known_vectors():
    assert _b58encode(b"") == ""
    assert _b58encode(b"\x00") == "1"
    assert _b58encode(b"\x00" * 32) == "1" * 32   # 32 zero bytes -> 32 leading '1's
    assert _b58encode(bytes([58])) == "21"        # 58 = 1*58 + 0


def test_pubkey_at_slices_decodes_and_b58_encodes():
    raw = bytes(range(40))                          # deterministic 40-byte blob
    data_b64 = base64.b64encode(raw).decode()
    assert _pubkey_at(data_b64, 8) == _b58encode(raw[8:40])   # pubkey = 32 bytes at offset 8


def test_raydium_v4_offset_decodes_known_lp_mint():
    fx = _FX["raydium_v4"]
    assert RAYDIUM_V4_LP_MINT_OFFSET == fx["offset"]
    assert _pubkey_at(fx["data_b64"], RAYDIUM_V4_LP_MINT_OFFSET) == fx["lp_mint"]


def test_raydium_cpmm_offset_decodes_known_lp_mint():
    fx = _FX["raydium_cpmm"]
    assert RAYDIUM_CPMM_LP_MINT_OFFSET == fx["offset"]
    assert _pubkey_at(fx["data_b64"], RAYDIUM_CPMM_LP_MINT_OFFSET) == fx["lp_mint"]


def test_verify_fungible_burned_is_secured():
    fx = _FX["raydium_v4"]
    ev = verify_fungible(_burned_client(fx), PoolRef(fx["pool"], "raydium", 50_000.0),
                         "raydium_v4", RAYDIUM_V4_LP_MINT_OFFSET)
    assert ev.secured is True
    assert ev.method == "lp_mint_burned"
    assert ev.lp_mint == fx["lp_mint"]
    assert ev.venue == "raydium_v4"


def test_verify_fungible_withdrawable_is_not_secured():
    fx = _FX["raydium_v4"]

    class _C:
        def get_account_info(self, addr, *, encoding="jsonParsed"):
            if addr == fx["pool"]:
                return {"data": [fx["data_b64"], "base64"]}
            return {"data": {"parsed": {"info": {"owner": "deployerWallet"}}}}

        def get_token_supply(self, mint):
            return 1000

        def get_token_largest_accounts(self, mint):
            return [{"address": "TA", "amount": "1000"}]

    ev = verify_fungible(_C(), PoolRef(fx["pool"], "raydium", 50_000.0),
                         "raydium_v4", RAYDIUM_V4_LP_MINT_OFFSET)
    assert ev.secured is False and ev.method == "withdrawable"


def test_verify_fungible_locker_held_is_secured_locked():
    fx = _FX["raydium_v4"]
    locker = next(iter(LP_LOCKERS))

    class _C:
        def get_account_info(self, addr, *, encoding="jsonParsed"):
            if addr == fx["pool"]:
                return {"data": [fx["data_b64"], "base64"]}
            return {"data": {"parsed": {"info": {"owner": locker}}}}

        def get_token_supply(self, mint):
            return 1000

        def get_token_largest_accounts(self, mint):
            return [{"address": "TA", "amount": "1000"}]

    ev = verify_fungible(_C(), PoolRef(fx["pool"], "raydium", 50_000.0),
                         "raydium_v4", RAYDIUM_V4_LP_MINT_OFFSET)
    assert ev.secured is True and ev.method.startswith("lp_locked:")


def test_analyzer_routes_raydium_and_aggregates_secured():
    fx = _FX["raydium_v4"]
    ray_v4 = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"

    class _Dex:
        def token_pairs(self, mint):
            return [{"pairAddress": fx["pool"], "dexId": "raydium", "liquidity": {"usd": 50_000.0}}]

    class _Helius:
        def get_account_info(self, addr, *, encoding="jsonParsed"):
            if addr == fx["pool"]:
                return {"data": [fx["data_b64"], "base64"]} if encoding == "base64" else {"owner": ray_v4}
            return {"data": {"parsed": {"info": {"owner": INCINERATOR}}}}

        def get_token_supply(self, mint):
            return 1000

        def get_token_largest_accounts(self, mint):
            return [{"address": "TA", "amount": "1000"}]

    out = LpAnalyzer(_Dex()).assess(_Helius(), "mintA")
    assert out.status is LpStatus.SECURED
    assert out.evidence and out.evidence[0].venue == "raydium_v4"


def test_analyzer_unpinned_venue_is_unknown():
    clmm = "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK"

    class _Dex:
        def token_pairs(self, mint):
            return [{"pairAddress": "CLMMP", "dexId": "raydium", "liquidity": {"usd": 50_000.0}}]

    class _Helius:
        def get_account_info(self, addr, *, encoding="jsonParsed"):
            return {"owner": clmm}

    out = LpAnalyzer(_Dex()).assess(_Helius(), "mintA")
    assert out.status is LpStatus.UNKNOWN
    assert out.evidence[0].method == "position_nft_unverified"


def test_analyzer_discovery_failure_is_unknown():
    class _Dex:
        def token_pairs(self, mint):
            raise AggregatorError("down")

    out = LpAnalyzer(_Dex()).assess(object(), "mintA")
    assert out.status is LpStatus.UNKNOWN
    assert out.evidence[0].method == "discovery_failed"
