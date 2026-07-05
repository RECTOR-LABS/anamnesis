"""Registration + startup smoke for the A.8 FastMCP entrypoint.

Loads mcp/solana_forensics_mcp.py (which lives outside the importable src/ tree because it is
spawned as a standalone stdio script) and asserts (a) the five forensic tools register on the
FastMCP server, and (b) main() fails fast on a missing Helius key and closes the HTTP client on
shutdown. Requires the mcp package — skipped in CI, which installs a pinned subset without it
(mirrors test_agent_tool_registration.py's qwen_agent guard).
"""
from __future__ import annotations

import asyncio
import importlib.util
import pathlib

import pytest

pytest.importorskip("mcp.server.fastmcp")  # skip in CI: the mcp SDK is absent there, and the
# repo's own top-level mcp/ dir (on sys.path via pythonpath=".") is a namespace pkg, not the SDK —
# so a plain importorskip("mcp") would NOT skip. Guard on the actual dependency the entrypoint needs.

_ENTRYPOINT = pathlib.Path(__file__).resolve().parents[1] / "mcp" / "solana_forensics_mcp.py"


def _load_module():
    """Exec the standalone entrypoint as a fresh module (fresh _client singleton each call)."""
    spec = importlib.util.spec_from_file_location("solana_forensics_mcp", _ENTRYPOINT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_server():
    return _load_module().server


def test_all_forensic_tools_register():
    server = _load_server()
    # Assert via the public async list_tools() (Tool objects), not the private _tool_manager.
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert names == {"get_token_profile", "get_deployer", "get_holders",
                     "trace_funding", "get_deployer_token_history"}


def test_main_fails_fast_when_helius_key_missing(monkeypatch):
    """A missing key must abort startup BEFORE serving — a config fault should fail loudly,
    not be deferred to the first tool call (where it would masquerade as a per-mint error)."""
    module = _load_module()
    monkeypatch.delenv("ANAMNESIS_HELIUS_API_KEY", raising=False)
    served = []
    monkeypatch.setattr(module.server, "run", lambda *a, **k: served.append(True))
    with pytest.raises(RuntimeError, match="ANAMNESIS_HELIUS_API_KEY"):
        module.main()
    assert served == []  # never reached server.run()


def test_main_closes_helius_client_on_shutdown(monkeypatch):
    """The singleton HTTP client must be closed when serving ends (no leak), and is pre-built
    at startup single-threaded so the lazy _helius() init can't race under concurrent calls."""
    module = _load_module()
    monkeypatch.setenv("ANAMNESIS_HELIUS_API_KEY", "dummy-key-for-test")
    monkeypatch.setattr(module.server, "run", lambda *a, **k: None)
    module.main()
    assert module._client is not None  # singleton pre-built at startup, not lazily on 1st call
    assert module._client._client.is_closed  # httpx client closed on shutdown
