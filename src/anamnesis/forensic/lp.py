"""LP-securedness verification (Phase 1) — pure verdict logic + on-chain verifiers.

Discovery (forensic/pools.py) enumerates a mint's pools; here each pool is routed by its
owning program to a per-venue verifier that proves securedness against Helius reads, and the
results compose by conservative precedence into an LpAssessment. Burn = LP held by the
incinerator (supply unchanged) or burned out of supply; lock = LP held by a curated, cited
locker program. Aggregator output is never trusted for the verdict — only on-chain reads are.
"""
from __future__ import annotations

# Canonical Solana burn account: tokens sent here are unspendable (supply is NOT decremented).
INCINERATOR = "1nc1nerator11111111111111111111111111111111"

# Cite-or-omit, MAINNET program ids only (see design D6 for sources). owner(LP holder) in keys => locked.
LP_LOCKERS: dict[str, str] = {
    "LocpQgucEQHbqNABEYvBvwoxCPsSbG91A1QaQhQQqjn": "jupiter_lock",
    "strmRqUCoQUgGUan5YhzUZa6KqdzwX5L6FpUxfmKg5m": "streamflow",
    "LockrWmn6K5twhz3y9w1dQERbmgSaRkfnTeTKbpofwE": "raydium_lock",
    "GsSCS3vPWrtJ5Y9aEVVT65fmrex5P5RGHXdZvsdbWgfo": "uncx",
    "UNCX77nZrA3TdAxMEggqG18xxpgiNGT6iqyynPwpoxN": "uncx",
    "UNCXdvMRxvz91g3HqFmpZ5NgmL77UH4QRM4NfeL4mQB": "uncx",
    "UNCXrB8cZXnmtYM1aSo1Wx3pQaeSZYuF2jCTesXvECs": "uncx",
}

SECURED_FRACTION_THRESHOLD = 0.95  # >= this fraction of current LP supply burned+locked => pool secured
DUST_LIQUIDITY_USD = 1_000.0       # pools below this are recorded but never drive the verdict (decoy guard)


def secured_fraction(holders: list[dict], supply: int) -> float:
    """Fraction of *current* LP supply that is immobilized (incinerator-held or locker-held).

    ``holders`` are top LP-token holders already annotated with their resolved owner. The
    denominator is current circulating supply, so a partial SPL-burn that leaves withdrawable
    LP correctly reads below 1.0. Returns 0.0 on zero/unknown supply.
    """
    if not supply:
        return 0.0
    secured = 0
    for h in holders:
        owner = h.get("owner")
        if owner == INCINERATOR or owner in LP_LOCKERS:
            secured += int(h.get("amount") or 0)
    return secured / supply
