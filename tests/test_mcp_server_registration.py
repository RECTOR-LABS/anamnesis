"""Registration smoke for the A.8 FastMCP entrypoint.

Loads mcp/solana_forensics_mcp.py (which lives outside the importable src/ tree because it is
spawned as a standalone stdio script) and asserts the three forensic tools register on the
FastMCP server. Requires the mcp package — skipped in CI, which installs a pinned subset
without it (mirrors test_agent_tool_registration.py's qwen_agent guard).
"""
from __future__ import annotations

import asyncio
import importlib.util
import pathlib

import pytest

pytest.importorskip("mcp")  # skipped in CI (mcp not installed there)

_ENTRYPOINT = pathlib.Path(__file__).resolve().parents[1] / "mcp" / "solana_forensics_mcp.py"


def _load_server():
    spec = importlib.util.spec_from_file_location("solana_forensics_mcp", _ENTRYPOINT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.server


def test_three_forensic_tools_register():
    server = _load_server()
    # Assert via the public async list_tools() (Tool objects), not the private _tool_manager.
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert names == {"get_token_profile", "get_deployer", "get_holders"}
