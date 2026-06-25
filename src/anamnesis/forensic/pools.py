"""Pool discovery — keyless DexScreener enumeration of a mint's pools.

DexScreener returns the pool/pair address, a bare ``dexId``, and indexed USD liquidity — but
NOT the LP mint (resolved on-chain later) and not an unambiguous venue (V4/CPMM/CLMM all read
``dexId == "raydium"``). So this layer only enumerates; venue routing and securedness are
on-chain (forensic/lp.py). The interface leaves a seam for a GeckoTerminal fallback (Phase 2).
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

DEXSCREENER_BASE = "https://api.dexscreener.com"


class AggregatorError(RuntimeError):
    """DexScreener was unreachable or returned an unusable payload."""


@dataclass
class PoolRef:
    pool: str
    dex_id: str
    liquidity_usd: float | None


class DexScreenerClient:
    """Minimal keyless DexScreener client (token-pairs lookup)."""

    def __init__(self, *, timeout: float = 20.0) -> None:
        self._client = httpx.Client(timeout=timeout, base_url=DEXSCREENER_BASE)

    def __enter__(self) -> DexScreenerClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def token_pairs(self, mint: str) -> list[dict]:
        """All Solana pairs for a mint; raises AggregatorError on transport/shape failure."""
        try:
            resp = self._client.get(f"/token-pairs/v1/solana/{mint}")
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:  # ValueError = bad JSON
            raise AggregatorError(f"dexscreener token-pairs failed: {e}") from e
        if not isinstance(data, list):
            raise AggregatorError(
                f"dexscreener token-pairs: expected a list, got {type(data).__name__}"
            )
        return data


def discover_pools(client: DexScreenerClient, mint: str) -> list[PoolRef]:
    """Enumerate a mint's pools as PoolRefs; pairs without an address are skipped."""
    out: list[PoolRef] = []
    for p in client.token_pairs(mint):
        addr = p.get("pairAddress")
        if not addr:
            continue
        usd = (p.get("liquidity") or {}).get("usd")
        out.append(PoolRef(pool=addr, dex_id=p.get("dexId") or "", liquidity_usd=usd))
    return out
