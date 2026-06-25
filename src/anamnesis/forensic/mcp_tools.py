"""Forensic MCP tool handlers (A.8) — pure over an injected HeliusClient.

Each handler composes the tested helius.py reads into a JSON-able dict for the MCP server to
return. The ``@_forensic_read`` decorator is the single boundary that (a) rejects a blank mint
and (b) degrades any Helius RPC failure OR malformed/edge payload into a structured
``{"error", "mint"}`` result — so a bad read produces an LLM-readable signal instead of
crashing the stdio loop. The client is injected, so handlers are unit-tested with a canned
fake client (no network, no mcp package) and run in CI. The thin entrypoint
(mcp/solana_forensics_mcp.py) owns the live client.
"""
from __future__ import annotations

import functools
from collections.abc import Callable

import httpx

from .helius import (
    HeliusClient,
    HeliusError,
    _lp_unanalyzed,
    build_token_profile,
    classify_funder,
    created_mints,
    funder_of,
    holder_count,
    resolve_origin,
    top_holder_pct,
)

# Degrade (don't crash the stdio loop) on a Helius RPC error OR a malformed/edge payload whose
# shape breaks parsing: a non-numeric supply (ValueError), a null result or a non-dict holder
# entry (AttributeError/TypeError), a missing field (KeyError). These handlers ingest
# adversarial on-chain data, so an unexpected shape must surface as a readable error rather
# than a traceback. Programmer errors on the happy path are still caught by the exact-dict
# unit tests (they assert the full result, so a real bug fails them instead of being masked).
_DEGRADE_ON = (HeliusError, httpx.HTTPError, ValueError, TypeError, AttributeError, KeyError)


def _forensic_read(fn: Callable[..., dict]) -> Callable[..., dict]:
    """Wrap a forensic handler so it never raises past the tool boundary: validate the mint,
    then turn any degradable failure into a structured ``{"error", "mint"}`` dict."""

    @functools.wraps(fn)
    def wrapper(client: HeliusClient, mint: str, *args: object, **kwargs: object) -> dict:
        if not isinstance(mint, str) or not mint.strip():
            return {"error": "invalid mint: expected a non-empty address string", "mint": mint}
        try:
            return fn(client, mint, *args, **kwargs)
        except _DEGRADE_ON as e:
            return {"error": str(e), "mint": mint}

    return wrapper


@_forensic_read
def token_profile_dict(client: HeliusClient, mint: str, *, lp_resolver=_lp_unanalyzed) -> dict:
    """Full forensic profile for a mint (authorities, liquidity, holders, deployer, created_at).

    ``lp_resolver`` is injected by the entrypoint with the real LpAnalyzer; the default reports
    LP status ``unknown`` (not analyzed)."""
    p = build_token_profile(client, mint, lp_resolver=lp_resolver)
    return {
        "mint": p.mint,
        "deployer": p.deployer,
        "created_at": p.created_at,
        "mint_authority": p.mint_authority,
        "freeze_authority": p.freeze_authority,
        "lp": {
            "status": p.lp.status.value,
            "evidence": [
                {"venue": e.venue, "pool": e.pool, "lp_mint": e.lp_mint, "method": e.method,
                 "secured": e.secured, "detail": e.detail, "liquidity_usd": e.liquidity_usd,
                 "citation": e.citation}
                for e in p.lp.evidence
            ],
        },
        "top_holder_pct": p.top_holder_pct,
        "holder_count": p.holder_count,
    }


@_forensic_read
def deployer_dict(client: HeliusClient, mint: str) -> dict:
    """The mint's deployer wallet (memory key) + creation time; nulls when unresolved."""
    deployer, created_at = resolve_origin(client, mint)
    return {"mint": mint, "deployer": deployer, "created_at": created_at}


@_forensic_read
def holders_dict(client: HeliusClient, mint: str, *, top_n: int = 10) -> dict:
    """Holder concentration: total holders, top-holder %, and the largest accounts (<= top_n)."""
    top_n = max(0, top_n)  # negative top_n must not slice from the wrong end (drop the top holder)
    asset = client.get_asset(mint)
    supply = int((asset.get("token_info") or {}).get("supply") or 0)
    largest = client.get_token_largest_accounts(mint)
    count = holder_count(client, mint)
    return {
        "mint": mint,
        "holder_count": count,
        "top_holder_pct": top_holder_pct(largest, supply),
        "largest": [
            {"address": a.get("address"), "amount": a.get("amount")} for a in largest[:top_n]
        ],
    }


@_forensic_read
def trace_funding_dict(client: HeliusClient, mint: str) -> dict:
    """The deployer's 1-hop funding source: the wallet that funded the deployer and its category
    (cex/bridge/mixer/unknown). funder is null when no inbound funder is identifiable."""
    deployer, _ = resolve_origin(client, mint)
    funder, funded_at = funder_of(client, deployer)
    return {
        "mint": mint,
        "deployer": deployer,
        "funder": funder,
        "source_type": classify_funder(funder),
        "funded_at": funded_at,
    }


@_forensic_read
def deployer_token_history_dict(client: HeliusClient, mint: str) -> dict:
    """Other token mints the deployer has created (a live serial-deployer scan), with a
    ``truncated`` flag when the bounded scan stopped on a cap."""
    deployer, _ = resolve_origin(client, mint)
    mints, truncated = created_mints(client, deployer)
    return {
        "mint": mint,
        "deployer": deployer,
        "created_mints": mints,
        "count": len(mints),
        "truncated": truncated,
    }
