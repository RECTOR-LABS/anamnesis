"""Solana Forensics MCP server (A.8) — a thin FastMCP stdio wrapper over the tested forensic
core. Spawned by the Qwen-Agent Assistant as a child process; exposes three grounded Solana
reads as MCP tools. ANAMNESIS_HELIUS_API_KEY is read from the inherited process env (never argv).

Run standalone (stdio):  python mcp/solana_forensics_mcp.py
"""
# NOTE: deliberately NO `from __future__ import annotations` here. FastMCP's
# Tool.from_function reads raw inspect.signature annotations (not get_type_hints), so
# stringized annotations would break tool registration (issubclass('str', Context)).
from mcp.server.fastmcp import FastMCP

from anamnesis import config
from anamnesis.forensic.helius import HeliusClient
from anamnesis.forensic.mcp_tools import deployer_dict, holders_dict, token_profile_dict

# Instance named `server` (not `mcp`) to avoid shadowing the imported package.
server = FastMCP("solana-forensics")

_client: HeliusClient | None = None


def _helius() -> HeliusClient:
    """Lazily build one HeliusClient from env, reused across tool calls in this process."""
    global _client
    if _client is None:
        _client = HeliusClient(config.require("ANAMNESIS_HELIUS_API_KEY"))
    return _client


@server.tool()
def get_token_profile(mint: str) -> dict:
    """Full forensic profile for a token mint: authorities (null == renounced), liquidity,
    holder concentration, the deployer wallet, and the creation time."""
    return token_profile_dict(_helius(), mint)


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


if __name__ == "__main__":
    server.run()
