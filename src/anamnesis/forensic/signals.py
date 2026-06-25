"""Pure forensic risk-signal extraction over a token profile.

No I/O — `assess_token_signals` maps a `TokenProfile` (built elsewhere from
on-chain reads) to a list of `Signal`s. Kept pure so it is fully unit-testable
without a network or a database.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

HOLDER_CONCENTRATION_THRESHOLD = 25.0  # percent owned by the top non-LP holder


class LpStatus(str, Enum):
    SECURED = "secured"
    NOT_SECURED = "not_secured"
    UNKNOWN = "unknown"


@dataclass
class LpEvidence:
    venue: str            # raydium_v4 | raydium_cpmm | meteora_damm_v1 | pumpswap | pumpfun_curve | unknown
    pool: str             # pool / pair address
    lp_mint: str | None   # resolved LP mint (None for bonding curve / unresolved)
    method: str           # lp_mint_burned | lp_locked:<locker> | bonding_curve_custody | withdrawable | position_nft_unverified | discovery_failed | verify_failed
    secured: bool | None  # True | False | None(=unknown for this pool)
    detail: str
    liquidity_usd: float | None = None
    citation: str | None = None


@dataclass
class LpAssessment:
    status: LpStatus
    evidence: list[LpEvidence] = field(default_factory=list)


@dataclass
class TokenProfile:
    mint: str
    deployer: str | None  # None == deployer could not be resolved
    mint_authority: str | None  # None == renounced (safe)
    freeze_authority: str | None  # None == renounced (safe)
    lp_secured: bool  # liquidity burned or locked
    top_holder_pct: float  # 0..100, largest non-LP holder
    holder_count: int
    created_at: str | None = None


@dataclass
class Signal:
    code: str
    severity: str  # "low" | "medium" | "high"
    detail: str


def assess_token_signals(p: TokenProfile) -> list[Signal]:
    out: list[Signal] = []
    if p.mint_authority is not None:
        out.append(Signal(
            "MINT_AUTHORITY_ACTIVE", "high",
            f"Mint authority not renounced ({p.mint_authority}); supply can be inflated.",
        ))
    if p.freeze_authority is not None:
        out.append(Signal(
            "FREEZE_AUTHORITY_ACTIVE", "high",
            f"Freeze authority active ({p.freeze_authority}); holders can be frozen.",
        ))
    if not p.lp_secured:
        out.append(Signal(
            "LP_NOT_SECURED", "high",
            "Liquidity is neither burned nor locked; deployer can pull liquidity.",
        ))
    if p.top_holder_pct >= HOLDER_CONCENTRATION_THRESHOLD:
        out.append(Signal(
            "HOLDER_CONCENTRATION", "medium",
            f"Top holder owns {p.top_holder_pct:.1f}% (>= {HOLDER_CONCENTRATION_THRESHOLD:.0f}%).",
        ))
    return out
