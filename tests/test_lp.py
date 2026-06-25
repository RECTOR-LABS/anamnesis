from anamnesis.forensic.lp import INCINERATOR, LP_LOCKERS, secured_fraction

_LOCKER = next(iter(LP_LOCKERS))  # a curated locker program id


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
