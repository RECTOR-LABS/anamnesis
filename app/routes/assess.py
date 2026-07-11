"""POST /api/assess: the HTTP surface over the frozen engine's assess_and_act pipeline.

No engine logic lives here. The route validates the request, delegates to `app.deps.assess`
(looked up via the module — `from app import deps` then `deps.assess(...)`, never
`from app.deps import assess` — so tests can `monkeypatch.setattr(deps, "assess", ...)`), and
reshapes the result through `app.cards.verdict_card`.

Two boundaries this thin route DOES own (a public entry point per CLAUDE.md):
- Shape validation — a missing `mint` field 422s via pydantic; a present-but-malformed `mint`
  (empty, not base58) is rejected 400 here before any engine/Helius work runs.
- Live-read failure — `deps.assess` -> `build_lp_aware_profile` is NOT `@_forensic_read`-wrapped
  (unlike the lazy profile/deployer/funding routes), so a Helius 4xx/5xx/timeout, a 429-storm, or
  a base58-valid but nonexistent mint raises `HeliusError` out of the engine. That is degraded to
  a clean, actionable 502 here rather than surfacing as a raw 500.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from anamnesis.forensic.helius import HeliusError
from app import deps
from app.cards import verdict_card
from app.validation import valid_mint

router = APIRouter()


class AssessIn(BaseModel):
    mint: str


@router.post("/api/assess")
def post_assess(body: AssessIn) -> dict:
    if not valid_mint(body.mint):
        raise HTTPException(status_code=400, detail="mint must be a base58 Solana address")
    try:
        result = deps.assess(body.mint)
    except HeliusError:
        raise HTTPException(
            status_code=502,
            detail="could not read this token on-chain right now — please retry",
        ) from None
    return verdict_card(result, mint=body.mint, deployer=result.get("deployer"))
