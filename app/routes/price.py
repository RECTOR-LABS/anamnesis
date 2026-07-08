"""GET /api/price/{mint}: a minimal price sparkline for the dashboard, reconstructed from
DexScreener's priceChange buckets (see app.cards.price_points for the honest-approximation
rationale — the existing DexScreenerClient affords no real time-series endpoint).

Kept deliberately thin and NEVER 500s: `DexScreenerClient.token_pairs` (anamnesis.forensic.
pools) raises `AggregatorError` on any transport/shape failure (timeout, non-2xx, bad JSON),
which is caught here and turned into an empty points list — the same well-shaped "miss"
response `price_points` itself returns for an empty/garbage pair list — so the sparkline
component always gets `{"points": [...]}`, never a 500, whatever DexScreener does.
`deps.get_dex()` is resolved via the module (`from app import deps`), never
`from app.deps import get_dex`, so tests can monkeypatch `deps.get_dex`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from anamnesis.forensic.pools import AggregatorError
from app import deps
from app.cards import price_points

router = APIRouter()


@router.get("/api/price/{mint}")
def get_price(mint: str) -> dict:
    try:
        pairs = deps.get_dex().token_pairs(mint)
    except AggregatorError:
        return {"points": []}
    return {"points": price_points(pairs, datetime.now(timezone.utc))}
