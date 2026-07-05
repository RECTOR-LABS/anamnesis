"""GET /api/deployer/{mint}: the deployer's serial-mint history (other tokens the same wallet
has created) for the dashboard's Pro-only deployer-history card, fetched lazily after the
verdict.

No engine logic lives here — `deployer_token_history_dict` (anamnesis.forensic.mcp_tools) is
`@_forensic_read`-decorated: it validates the mint and degrades any Helius RPC failure or
malformed payload to a structured {"error", "mint"} dict rather than raising (mcp_tools.py's
`_DEGRADE_ON`), and an unresolved deployer (resolve_origin turning up nothing) degrades further
still to a well-shaped empty history (`deployer: null, created_mints: [], count: 0`) via
`created_mints`' own `if not deployer: return [], False` guard — neither path ever raises. So
this route needs no try/except of its own: it just resolves the HeliusClient singleton via the
`deps` module (`from api import deps` then `deps.get_helius()`, never `from api.deps import
get_helius`, so tests can monkeypatch `deps.get_helius`) and returns the serializer's dict
verbatim, matching api/routes/graph.py's thin-over-a-degrading-engine philosophy.
"""
from __future__ import annotations

from fastapi import APIRouter

from anamnesis.forensic.mcp_tools import deployer_token_history_dict
from api import deps

router = APIRouter()


@router.get("/api/deployer/{mint}")
def get_deployer(mint: str) -> dict:
    return deployer_token_history_dict(deps.get_helius(), mint)
