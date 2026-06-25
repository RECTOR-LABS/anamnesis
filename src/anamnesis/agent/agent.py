"""Assemble the Anamnesis agent (A.9).

Wires the native memory tools (A.7) and the Solana forensics MCP server (A.8) into one
Qwen-Agent Assistant driven by qwen-max over the DashScope international, OpenAI-compatible
endpoint. The pure builders here carry the typo-prone config (model id, base URL, spawn
command, tool names) and are unit-tested in CI; build_agent() is the thin, qwen-agent-coupled
shell whose assembly test importorskips (CI installs no qwen-agent / mcp).
"""
import sys
from pathlib import Path

from .. import config

# Native @register_tool tools (A.7), resolved by name from Qwen-Agent's TOOL_REGISTRY once
# anamnesis.agent.tools is imported (build_agent triggers that import before constructing the
# Assistant). Order is cosmetic — resolution is by name.
NATIVE_TOOLS = ["recall", "remember", "assess_risk"]


def build_llm_cfg(api_key: str) -> dict:
    """The Qwen-Agent llm config (DashScope-intl, OpenAI-compatible). The key is injected, not
    read from env, so this stays pure and unit-testable without a real secret."""
    return {
        "model": config.QWEN_MODEL,
        "model_server": config.DASHSCOPE_BASE_URL,
        "api_key": api_key,
        "model_type": "oai",
        "generate_cfg": {"top_p": 0.8},
    }


def mcp_entrypoint_path() -> Path:
    """Absolute path to the A.8 MCP stdio entrypoint, resolved from this file's location so it
    holds regardless of the CWD the WebUI is launched from. Fails fast if the entrypoint is
    missing rather than letting Qwen-Agent spawn a doomed child on first tool call."""
    path = Path(__file__).resolve().parents[3] / "mcp" / "solana_forensics_mcp.py"
    if not path.is_file():
        raise RuntimeError(
            f"MCP entrypoint not found at {path}; expected mcp/solana_forensics_mcp.py at the "
            "repository root (preserved by `pip install -e .`)."
        )
    return path


def build_function_list(helius_api_key: str) -> list:
    """The Assistant's function_list: the forensic MCP server (spawned as a stdio child under
    this same interpreter, so it has anamnesis + mcp installed) plus the native memory tools by
    name. The key is injected (not read from env here) so this stays pure and unit-testable, and
    is handed to the child via the MCP server ``env`` block — the stdio SDK spawns the child with
    only a small safe allowlist (PATH, HOME, ...) and strips everything else, so the key must be
    passed explicitly: it is never inherited, and never travels via argv."""
    return [
        {
            "mcpServers": {
                "solana_forensics": {
                    "command": sys.executable,
                    "args": [str(mcp_entrypoint_path())],
                    "env": {"ANAMNESIS_HELIUS_API_KEY": helius_api_key},
                }
            }
        },
        *NATIVE_TOOLS,
    ]


def build_agent():
    """Assemble the Anamnesis Qwen-Agent Assistant: native memory tools (A.7) + the forensic
    MCP server (A.8), system instruction from prompts.py, qwen-max over DashScope-intl.

    Both secrets are resolved FIRST — before the qwen-agent import — so a missing key raises an
    actionable RuntimeError in this (parent) process, and those paths stay testable in CI (where
    qwen-agent is absent). The Helius key is then handed to the spawned MCP child via its ``env``
    block (see build_function_list); resolving it here makes a misconfigured deployment fail
    loudly at agent construction instead of as an opaque child "connection closed". Importing
    anamnesis.agent.tools fires its @register_tool decorators so the native tool names resolve
    against Qwen-Agent's TOOL_REGISTRY before the Assistant is built.
    """
    dashscope_key = config.require("ANAMNESIS_DASHSCOPE_API_KEY")
    helius_key = config.require("ANAMNESIS_HELIUS_API_KEY")

    from qwen_agent.agents import Assistant

    from . import tools  # noqa: F401 — import populates the @register_tool registry
    from .prompts import SYSTEM_INSTRUCTION

    return Assistant(
        llm=build_llm_cfg(dashscope_key),
        name="anamnesis",
        system_message=SYSTEM_INSTRUCTION,
        function_list=build_function_list(helius_key),
    )
