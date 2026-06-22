"""Pure forensic risk-signal extraction over a token profile.

No I/O — `assess_token_signals` maps a `TokenProfile` (built elsewhere from
on-chain reads) to a list of `Signal`s. Kept pure so it is fully unit-testable
without a network or a database.
"""
from __future__ import annotations

from dataclasses import dataclass

HOLDER_CONCENTRATION_THRESHOLD = 25.0  # percent owned by the top non-LP holder


@dataclass
class TokenProfile:
    mint: str
    deployer: str
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
