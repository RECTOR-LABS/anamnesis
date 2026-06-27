"""Assembly tests for the A.9 agent wiring.

The pure builders run everywhere (no qwen-agent import). build_agent() is exercised by a
guarded test that importorskips when qwen-agent/mcp are absent (CI installs neither). The
guard lives INSIDE that test so the CI-runnable tests in this file are not skipped with it.
"""
import os
import sys

import pytest

from anamnesis import config
from anamnesis.agent.agent import (
    build_function_list,
    build_llm_cfg,
    mcp_entrypoint_path,
)


def test_build_llm_cfg_is_dashscope_oai_with_injected_key():
    assert build_llm_cfg("dummy-key") == {
        "model": config.QWEN_MODEL,
        "model_server": config.DASHSCOPE_BASE_URL,
        "api_key": "dummy-key",
        "model_type": "oai",
        "generate_cfg": {"top_p": 0.8},
    }


def test_mcp_entrypoint_path_resolves_to_the_real_file():
    path = mcp_entrypoint_path()
    assert path.is_file()
    assert path.name == "solana_forensics_mcp.py"
    assert path.parent.name == "mcp"


def test_build_function_list_spawns_under_this_interpreter_then_native_tools():
    fl = build_function_list("dummy-helius-key")
    block = fl[0]["mcpServers"]["solana_forensics"]
    assert block["command"] == sys.executable
    assert len(block["args"]) == 1
    arg = block["args"][0]
    assert os.path.isabs(arg)
    assert os.path.isfile(arg)
    assert arg.endswith(os.path.join("mcp", "solana_forensics_mcp.py"))
    # The Helius key is handed to the child explicitly via env (the MCP stdio SDK strips
    # unlisted vars, so it cannot be inherited); it must never travel via argv.
    assert block["env"] == {"ANAMNESIS_HELIUS_API_KEY": "dummy-helius-key"}
    assert "dummy-helius-key" not in arg
    assert fl[1:] == ["recall", "remember", "assess_risk", "watchlist_add", "draft_alert",
                      "list_pending_alerts"]


def test_build_agent_missing_dashscope_key_raises_actionable_error(monkeypatch):
    # Runs in CI too: config.require() raises BEFORE the qwen-agent import is reached.
    monkeypatch.delenv("ANAMNESIS_DASHSCOPE_API_KEY", raising=False)
    from anamnesis.agent.agent import build_agent

    with pytest.raises(RuntimeError, match="ANAMNESIS_DASHSCOPE_API_KEY"):
        build_agent()


def test_build_agent_missing_helius_key_raises_actionable_error(monkeypatch):
    # Runs in CI too: both keys are resolved BEFORE the qwen-agent import, so a missing Helius
    # key fails loudly here (parent) with an actionable message — not as an opaque child spawn
    # failure. DashScope key is present so resolution reaches the Helius check.
    monkeypatch.setenv("ANAMNESIS_DASHSCOPE_API_KEY", "dummy-dashscope-key")
    monkeypatch.delenv("ANAMNESIS_HELIUS_API_KEY", raising=False)
    from anamnesis.agent.agent import build_agent

    with pytest.raises(RuntimeError, match="ANAMNESIS_HELIUS_API_KEY"):
        build_agent()


def test_build_agent_assembles_native_and_mcp_tools(monkeypatch):
    # Real wiring test: constructing the Assistant spawns the MCP stdio child under
    # sys.executable and lists its tools. The child fails fast without ANAMNESIS_HELIUS_API_KEY
    # (A.8h ⑦; unit-tested in test_mcp_server_registration.py), so a dummy is set here —
    # listing/registering tools does no network I/O, so a dummy key suffices.
    # Skipped in CI, which installs neither qwen-agent nor mcp.
    pytest.importorskip("qwen_agent")
    pytest.importorskip("mcp")
    monkeypatch.setenv("ANAMNESIS_DASHSCOPE_API_KEY", "dummy-key-for-construction")
    monkeypatch.setenv("ANAMNESIS_HELIUS_API_KEY", "dummy-key-for-construction")
    from anamnesis.agent.agent import build_agent

    agent = build_agent()
    assert agent.name == "anamnesis"
    assert {"recall", "remember", "assess_risk"} <= set(agent.function_map)
    # qwen-agent namespaces MCP tools by the server key ("solana_forensics") from
    # build_function_list, so the three forensic reads land under that prefix.
    assert {
        "solana_forensics-get_token_profile",
        "solana_forensics-get_deployer",
        "solana_forensics-get_holders",
    } <= set(agent.function_map)
