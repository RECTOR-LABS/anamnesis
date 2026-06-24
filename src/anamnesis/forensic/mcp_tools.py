"""Forensic MCP tool handlers (A.8) — pure over an injected HeliusClient.

Each handler composes the tested helius.py reads into a JSON-able dict for the MCP server to
return, and maps expected upstream failures (HeliusError / httpx errors) to a structured
``{"error", "mint"}`` result, so a bad read degrades into an LLM-readable signal instead of
crashing the stdio loop. The client is injected, so these are unit-tested with a canned fake
client — no network, no mcp package — and run in CI. The thin entrypoint
(mcp/solana_forensics_mcp.py) owns the live client.
"""
from __future__ import annotations

import httpx

from .helius import (
    HeliusClient,
    HeliusError,
    build_token_profile,
    holder_count,
    resolve_origin,
    top_holder_pct,
)

_UPSTREAM_ERRORS = (HeliusError, httpx.HTTPError)


def token_profile_dict(client: HeliusClient, mint: str) -> dict:
    """Full forensic profile for a mint (authorities, liquidity, holders, deployer, created_at)."""
    try:
        p = build_token_profile(client, mint)
    except _UPSTREAM_ERRORS as e:
        return {"error": str(e), "mint": mint}
    return {
        "mint": p.mint,
        "deployer": p.deployer,
        "created_at": p.created_at,
        "mint_authority": p.mint_authority,
        "freeze_authority": p.freeze_authority,
        "lp_secured": p.lp_secured,
        "top_holder_pct": p.top_holder_pct,
        "holder_count": p.holder_count,
    }


def deployer_dict(client: HeliusClient, mint: str) -> dict:
    """The mint's deployer wallet (memory key) + creation time; nulls when unresolved."""
    try:
        deployer, created_at = resolve_origin(client, mint)
    except _UPSTREAM_ERRORS as e:
        return {"error": str(e), "mint": mint}
    return {"mint": mint, "deployer": deployer, "created_at": created_at}


def holders_dict(client: HeliusClient, mint: str, *, top_n: int = 10) -> dict:
    """Holder concentration: total holders, top-holder %, and the largest accounts (<= top_n)."""
    try:
        asset = client.get_asset(mint)
        supply = int((asset.get("token_info") or {}).get("supply") or 0)
        largest = client.get_token_largest_accounts(mint)
        count = holder_count(client, mint)
    except _UPSTREAM_ERRORS as e:
        return {"error": str(e), "mint": mint}
    return {
        "mint": mint,
        "holder_count": count,
        "top_holder_pct": top_holder_pct(largest, supply),
        "largest": [
            {"address": a.get("address"), "amount": a.get("amount")} for a in largest[:top_n]
        ],
    }
