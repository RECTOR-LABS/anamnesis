"""GET /api/funding/{mint}: the deployer's 1-hop funding source (cex/bridge/mixer/unknown) for
the dashboard's Pro-only Funding Trail card, fetched lazily after the verdict.

No engine logic lives here — `trace_funding_dict` (anamnesis.forensic.mcp_tools) is
`@_forensic_read`-decorated: it validates the mint and degrades any Helius RPC failure or
malformed payload to a structured {"error", "mint"} dict rather than raising (mcp_tools.py's
`_DEGRADE_ON`), and an unresolved deployer degrades further still to a well-shaped null result
(`funder: null, source_type: "unknown"`) via `funder_of`'s own `if not deployer: return None,
None` guard and `classify_funder`'s `if not address: return "unknown"` — neither path ever
raises. So this route needs no try/except of its own: it just resolves the HeliusClient
singleton via the `deps` module (`from api import deps` then `deps.get_helius()`, never `from
api.deps import get_helius`, so tests can monkeypatch `deps.get_helius`) and returns the
serializer's dict verbatim, matching api/routes/graph.py's thin-over-a-degrading-engine
philosophy.
"""
from __future__ import annotations

from fastapi import APIRouter

from anamnesis.forensic.mcp_tools import trace_funding_dict
from api import deps

router = APIRouter()


@router.get("/api/funding/{mint}")
def get_funding(mint: str) -> dict:
    return trace_funding_dict(deps.get_helius(), mint)
