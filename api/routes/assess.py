"""POST /api/assess: the HTTP surface over the frozen engine's assess_and_act pipeline.

No engine logic lives here. The route validates the request body, delegates to
`api.deps.assess` (looked up via the module — `from api import deps` then `deps.assess(...)`,
never `from api.deps import assess` — so tests can `monkeypatch.setattr(deps, "assess", ...)`),
and reshapes the result through `api.cards.verdict_card`. Kept deliberately thin: the engine
already degrades gracefully on invalid/garbage mints (live-validated at Task 6 of
docs/plans/2026-07-04-ui-revamp.md), so no speculative try/except or "N/A" special-casing
belongs here — a missing `mint` field 422s automatically via pydantic, before this code runs.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from api import deps
from api.cards import verdict_card

router = APIRouter()


class AssessIn(BaseModel):
    mint: str


@router.post("/api/assess")
def post_assess(body: AssessIn) -> dict:
    result = deps.assess(body.mint)
    return verdict_card(result, mint=body.mint, deployer=result.get("deployer"))
