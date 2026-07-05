"""GET /api/profile/{mint}: the full forensic token profile (authorities, LP status, holder
concentration, deployer, created_at) for the dashboard's Pro-only Token Profile card, fetched
lazily after the verdict.

No engine logic lives here — `token_profile_dict` (anamnesis.forensic.mcp_tools) already
composes the grounded Helius reads into the wire-shaped dict; this route only resolves the
HeliusClient singleton via the `deps` module (`from api import deps` then `deps.get_helius()`,
never `from api.deps import get_helius`, so tests can monkeypatch `deps.get_helius`) and calls
the serializer with its DEFAULT `lp_resolver` (mcp_tools.py's `_lp_unanalyzed`) — so `lp.status`
always reports "unknown" here (not analyzed), which the dashboard renders as "unverified". The
LP-aware resolver (`deps.build_profile` / `build_lp_aware_profile`) is deliberately NOT wired in
here: that path is reserved for the assess verdict (api/routes/assess.py), not this lazy read.

`token_profile_dict` is `@_forensic_read`-decorated (mcp_tools.py) and therefore already
degrades a HeliusError/httpx.HTTPError/ValueError/TypeError/AttributeError/KeyError to a
structured {"error", "mint"} dict rather than raising past its own boundary — verified against
tests/test_mcp_tools.py::test_handlers_map_upstream_errors_to_structured_result. The try/except
below is defense-in-depth over that guarantee, mirroring api/routes/price.py's never-500
discipline: it catches the one error type documented on the client (HeliusError) rather than
swallowing every Exception, so a genuine programmer error still surfaces instead of being
masked.
"""
from __future__ import annotations

from fastapi import APIRouter

from anamnesis.forensic.helius import HeliusError
from anamnesis.forensic.mcp_tools import token_profile_dict
from api import deps

router = APIRouter()


@router.get("/api/profile/{mint}")
def get_profile(mint: str) -> dict:
    try:
        return token_profile_dict(deps.get_helius(), mint)
    except HeliusError:
        return {"mint": mint, "error": "profile unavailable"}
