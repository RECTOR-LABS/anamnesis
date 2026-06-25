from anamnesis.forensic.lp import (
    INCINERATOR,
    LP_LOCKERS,
    aggregate,
    largest_holders_with_owners,
    secured_fraction,
    venue_of,
)
from anamnesis.forensic.signals import LpEvidence, LpStatus

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
