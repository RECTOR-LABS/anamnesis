"""LP-securedness verification (Phase 1) — pure verdict logic + on-chain verifiers.

Discovery (forensic/pools.py) enumerates a mint's pools; here each pool is routed by its
owning program to a per-venue verifier that proves securedness against Helius reads, and the
results compose by conservative precedence into an LpAssessment. Burn = LP held by the
incinerator (supply unchanged) or burned out of supply; lock = LP held by a curated, cited
locker program. Aggregator output is never trusted for the verdict — only on-chain reads are.
"""
from __future__ import annotations

import base64

import httpx

from .helius import HeliusError
from .pools import AggregatorError, PoolRef, discover_pools
from .signals import LpAssessment, LpEvidence, LpStatus

_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _b58encode(raw: bytes) -> str:
    """Base58-encode raw bytes (Solana pubkey encoding — no checksum). Inlined to avoid a
    runtime dependency the fixed-subset CI would not install (see project CI notes)."""
    n = int.from_bytes(raw, "big")
    out = ""
    while n > 0:
        n, rem = divmod(n, 58)
        out = _B58_ALPHABET[rem] + out
    pad = len(raw) - len(raw.lstrip(b"\x00"))  # leading zero bytes -> leading '1's
    return "1" * pad + out


def _pubkey_at(data_b64: str, offset: int) -> str:
    """Decode the base58 pubkey of the 32 bytes at ``offset`` in base64 account data."""
    raw = base64.b64decode(data_b64)
    return _b58encode(raw[offset:offset + 32])

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

# Owning-program -> venue label. Routing by on-chain owner is the grounded alternative to the
# aggregator's ambiguous dexId (V4/CPMM/CLMM all read dexId == "raydium").
PROGRAM_TO_VENUE: dict[str, str] = {
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "raydium_v4",
    "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C": "raydium_cpmm",
    "Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB": "meteora_damm_v1",
    "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA": "pumpswap",
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": "pumpfun_curve",
}
FUNGIBLE_LP_VENUES = frozenset({"raydium_v4", "raydium_cpmm", "meteora_damm_v1", "pumpswap"})

# lp_mint byte offsets in each pool's account layout — pinned against live fixtures
# (tests/fixtures/lp_pool_accounts.json); see test_*_offset_decodes_known_lp_mint.
RAYDIUM_V4_LP_MINT_OFFSET = 464    # AmmInfo.lp_mint
RAYDIUM_CPMM_LP_MINT_OFFSET = 136  # PoolState.lp_mint (after 8-byte Anchor discriminator)


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


def aggregate(evidence: list[LpEvidence], *, dust_usd: float = DUST_LIQUIDITY_USD) -> LpStatus:
    """Compose per-pool evidence by conservative precedence: NOT_SECURED > UNKNOWN > SECURED.

    Only non-dust pools drive the verdict (a dust 'burned' decoy can't hide a deep unsecured
    pool, and a dust unsecured pool can't flag an otherwise-secured token). With no non-dust
    pool, or any non-dust pool we couldn't determine, the honest answer is UNKNOWN.
    """
    if not evidence:
        return LpStatus.UNKNOWN
    nondust = [e for e in evidence if (e.liquidity_usd or 0.0) >= dust_usd]
    if any(e.secured is False for e in nondust):
        return LpStatus.NOT_SECURED
    if not nondust or any(e.secured is None for e in nondust):
        return LpStatus.UNKNOWN
    return LpStatus.SECURED


def venue_of(helius, pool: str) -> str:
    """Classify a pool by its owning program (on-chain), else 'unknown'."""
    owner = helius.get_account_info(pool).get("owner")
    return PROGRAM_TO_VENUE.get(owner, "unknown")


def token_account_owner(helius, token_account: str) -> str | None:
    """The wallet/program that owns an SPL token account (jsonParsed ``info.owner``)."""
    info = helius.get_account_info(token_account)
    data = info.get("data")
    parsed = (data.get("parsed") or {}) if isinstance(data, dict) else {}
    return (parsed.get("info") or {}).get("owner")


def largest_holders_with_owners(helius, lp_mint: str) -> list[dict]:
    """Top LP-token holders annotated with their resolved owner (for secured_fraction)."""
    out: list[dict] = []
    for acc in helius.get_token_largest_accounts(lp_mint):
        out.append({"owner": token_account_owner(helius, acc.get("address")), "amount": acc.get("amount")})
    return out


def _classify(frac: float, locker_owner: str | None) -> tuple[bool, str]:
    """Map a secured fraction + any locker owner to (secured, method)."""
    if locker_owner:
        return True, f"lp_locked:{LP_LOCKERS.get(locker_owner, 'locker')}"
    if frac >= SECURED_FRACTION_THRESHOLD:
        return True, "lp_mint_burned"
    return False, "withdrawable"


def verify_fungible(helius, pool: PoolRef, venue: str, lp_mint_offset: int) -> LpEvidence:
    """Resolve a fungible pool's LP mint on-chain, then prove burned/locked vs withdrawable."""
    acct = helius.get_account_info(pool.pool, encoding="base64")
    data = acct.get("data")
    data_b64 = data[0] if isinstance(data, list) and data else None
    if not data_b64:
        return LpEvidence(venue, pool.pool, None, "verify_failed", None,
                          "pool account had no decodable data", pool.liquidity_usd)
    lp_mint = _pubkey_at(data_b64, lp_mint_offset)
    supply = helius.get_token_supply(lp_mint)
    if supply == 0:
        # Zero circulating LP == a full SPL burn: with real reserves the liquidity is locked
        # forever (no LP left to redeem). With no reserves it is a defunct/never-seeded pool.
        if (pool.liquidity_usd or 0.0) >= DUST_LIQUIDITY_USD:
            return LpEvidence(venue, pool.pool, lp_mint, "lp_mint_burned", True,
                              f"{venue} LP fully burned: zero circulating LP supply; "
                              "liquidity permanently locked.", pool.liquidity_usd, citation=lp_mint)
        return LpEvidence(venue, pool.pool, lp_mint, "verify_failed", None,
                          "zero LP supply and no real reserves (defunct pool)", pool.liquidity_usd)
    holders = largest_holders_with_owners(helius, lp_mint)
    frac = secured_fraction(holders, supply)
    locker_owner = next((h["owner"] for h in holders if h.get("owner") in LP_LOCKERS), None)
    secured, method = _classify(frac, locker_owner)
    note = " (lock duration unverified — Phase 1)" if method.startswith("lp_locked") else ""
    detail = (f"{venue} LP {'secured' if secured else 'withdrawable'}: "
              f"{frac:.0%} of supply burned/locked via {method}{note}.")
    return LpEvidence(venue, pool.pool, lp_mint, method, secured, detail, pool.liquidity_usd,
                      citation=lp_mint)


# Venues whose lp_mint offset is pinned (and thus on-chain-verifiable). Extended per venue.
_VENUE_OFFSETS = {
    "raydium_v4": RAYDIUM_V4_LP_MINT_OFFSET,
    "raydium_cpmm": RAYDIUM_CPMM_LP_MINT_OFFSET,
}
# A per-pool read may hit an RPC error or an unexpected on-chain shape; degrade that pool to
# 'unknown' rather than crash the whole assessment (the verdict stays honest, never false-secure).
_VERIFY_DEGRADE_ON = (
    HeliusError, httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError, IndexError,
)


class LpAnalyzer:
    """Discover a mint's pools and prove per-pool securedness on-chain into an LpAssessment."""

    def __init__(self, dex) -> None:
        self._dex = dex

    def assess(self, helius, mint: str) -> LpAssessment:
        try:
            pools = discover_pools(self._dex, mint)
        except AggregatorError as e:
            return LpAssessment(LpStatus.UNKNOWN, [LpEvidence(
                "unknown", "", None, "discovery_failed", None, f"pool discovery failed: {e}")])
        evidence = [self._verify(helius, p) for p in pools]
        return LpAssessment(aggregate(evidence), evidence)

    def _verify(self, helius, pool: PoolRef) -> LpEvidence:
        try:
            venue = venue_of(helius, pool.pool)
            if venue in _VENUE_OFFSETS:
                return verify_fungible(helius, pool, venue, _VENUE_OFFSETS[venue])
            return LpEvidence(venue, pool.pool, None, "position_nft_unverified", None,
                              "venue not yet on-chain-verifiable (position-NFT or Phase-2 venue).",
                              pool.liquidity_usd)
        except _VERIFY_DEGRADE_ON as e:
            return LpEvidence("unknown", pool.pool, None, "verify_failed", None,
                              f"pool verification failed: {e}", pool.liquidity_usd)
