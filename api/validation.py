"""Input validation for the public API surface.

CLAUDE.md mandates validating public entry points; the dashboard also validates client-side, so
this is the defense-in-depth server guard. Solana mint addresses are base58 (Bitcoin alphabet —
no 0, O, I, l) and 32-44 characters.
"""
from __future__ import annotations

import re

_MINT_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def valid_mint(mint: str | None) -> bool:
    """True iff `mint` is a syntactically valid base58 Solana address."""
    return bool(mint and _MINT_RE.fullmatch(mint))
