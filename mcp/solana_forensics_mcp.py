"""Solana Forensics MCP server (A.8) — a thin FastMCP stdio wrapper over the tested forensic
core. Spawned by the Qwen-Agent Assistant as a child process; exposes five grounded Solana
reads as MCP tools. ANAMNESIS_HELIUS_API_KEY is read from the process env — supplied by the
parent through the MCP server `env` config when spawned (the stdio SDK strips unlisted vars, so
it is passed explicitly, not inherited), or from your shell when run standalone. Never via argv.

Run standalone (stdio):  python mcp/solana_forensics_mcp.py
"""
# NOTE: deliberately NO `from __future__ import annotations` here. FastMCP's
# Tool.from_function reads raw inspect.signature annotations (not get_type_hints), so
# stringized annotations would break tool registration (issubclass('str', Context)).
from mcp.server.fastmcp import FastMCP

from anamnesis import config
from anamnesis.forensic.helius import HeliusClient
from anamnesis.forensic.lp import LpAnalyzer
from anamnesis.forensic.mcp_tools import (
    deployer_dict,
    deployer_token_history_dict,
    holders_dict,
    token_profile_dict,
    trace_funding_dict,
)
from anamnesis.forensic.pools import DexScreenerClient

# Instance named `server` (not `mcp`) to avoid shadowing the imported package.
server = FastMCP("solana-forensics")

_client: HeliusClient | None = None


def _helius() -> HeliusClient:
    """Lazily build one HeliusClient from env, reused across tool calls in this process."""
    global _client
    if _client is None:
        _client = HeliusClient(config.require("ANAMNESIS_HELIUS_API_KEY"))
    return _client


_dex: DexScreenerClient | None = None


def _dexscreener() -> DexScreenerClient:
    """Lazily build one keyless DexScreener client, reused across LP analyses in this process."""
    global _dex
    if _dex is None:
        _dex = DexScreenerClient()
    return _dex


@server.tool()
def get_token_profile(mint: str) -> dict:
    """Full forensic profile for a token mint: authorities (null == renounced), per-pool LP
    burn/lock evidence, holder concentration, the deployer wallet, and the creation time."""
    return token_profile_dict(_helius(), mint, lp_resolver=LpAnalyzer(_dexscreener()).assess)


@server.tool()
def get_deployer(mint: str) -> dict:
    """Resolve the wallet that deployed a mint (its memory key) and the creation timestamp.
    deployer is null when unresolved or only a shared launchpad authority is found."""
    return deployer_dict(_helius(), mint)


@server.tool()
def get_holders(mint: str, top_n: int = 10) -> dict:
    """Holder concentration for a mint: total holders, top-holder percentage, and the
    largest token accounts (up to top_n)."""
    return holders_dict(_helius(), mint, top_n=top_n)


@server.tool()
def trace_funding(mint: str) -> dict:
    """Classify how the mint's deployer was funded: the 1-hop funding wallet and whether it is a
    known CEX, bridge, or mixer (else unknown). Mixer funding is a strong rug signal."""
    return trace_funding_dict(_helius(), mint)


@server.tool()
def get_deployer_token_history(mint: str) -> dict:
    """Other token mints the deployer has created — a live on-chain scan that surfaces serial
    deployers. Bounded; the `truncated` flag marks a partial scan."""
    return deployer_token_history_dict(_helius(), mint)


def main() -> None:
    """Validate config and open the Helius client BEFORE serving, then serve until shutdown.

    Resolving ``ANAMNESIS_HELIUS_API_KEY`` here makes a missing/invalid key fail loudly at
    startup instead of surfacing as a per-mint tool error on the first call. Building the
    singleton in this single-threaded ``with`` (rather than lazily inside a tool call) both
    pre-warms it past the check-then-act race in ``_helius`` and closes the underlying HTTP
    client on shutdown.
    """
    with _helius():
        try:
            server.run()
        finally:
            if _dex is not None:
                _dex.close()


if __name__ == "__main__":
    main()
