"""Live smoke for the A.7 Qwen-Agent tool wrappers.

Runs only where qwen-agent is installed; CI installs a fixed dep subset that omits it
(see the guard below), so this is skipped there — just as the pure handlers in
test_agent_tools.py cover the behaviour everywhere. Here we validate the thin
``@register_tool`` adaptation layer that cannot be exercised without qwen-agent: that the
tools register under the right names and schema, and that ``call()`` routes JSON args
through to the pure handler with the write-path discipline intact.
"""
import json

import pytest

pytest.importorskip("qwen_agent")  # skipped in CI (qwen-agent not installed there)

from qwen_agent.tools.base import TOOL_REGISTRY  # noqa: E402

from anamnesis.agent import tools  # noqa: E402
from anamnesis.memory.graph import ForensicMemory  # noqa: E402
from anamnesis.memory.repository import InMemoryRepository  # noqa: E402


def test_all_three_tools_register():
    for name in ("recall", "remember", "assess_risk"):
        assert name in TOOL_REGISTRY


def test_acts_tools_are_registered():
    # B.1: the acting tools register alongside the read tools (assess_risk auto-acts).
    for name in ("watchlist_add", "draft_alert", "list_pending_alerts"):
        assert name in TOOL_REGISTRY


def test_cluster_graph_tool_is_registered():
    # B.2: the relationship-graph view tool.
    assert "cluster_graph" in TOOL_REGISTRY


def test_tool_parameter_schemas_name_their_required_args():
    assert TOOL_REGISTRY["recall"]().parameters[0]["name"] == "entity_key"
    assert TOOL_REGISTRY["remember"]().parameters[0]["name"] == "facts"
    assert TOOL_REGISTRY["assess_risk"]().parameters[0]["name"] == "mint"


def test_remember_tool_call_routes_to_handler_and_forces_claimed(monkeypatch):
    # The write-path discipline must survive the wrapper: a forged first_party claim
    # arriving through the registered tool is still downgraded to claimed.
    fake = ForensicMemory(InMemoryRepository())
    monkeypatch.setattr(tools, "_memory", lambda: fake)
    out = json.loads(
        TOOL_REGISTRY["remember"]().call(
            json.dumps({"facts": [
                {"type": "RUGGED", "src": "victim", "dst": "t",
                 "method": "first_party", "confidence": 1.0},
            ]})
        )
    )
    assert out["remembered"] == 1
    [e] = fake.recall("victim")
    assert e.provenance.method == "claimed"


def test_recall_tool_call_routes_to_handler(monkeypatch):
    fake = ForensicMemory(InMemoryRepository())
    tools.remember_handler(
        fake, [{"type": "SAME_CLUSTER", "src": "w", "dst": "x"}], "2026-02-01"
    )
    monkeypatch.setattr(tools, "_memory", lambda: fake)
    out = json.loads(TOOL_REGISTRY["recall"]().call(json.dumps({"entity_key": "w"})))
    assert out["entity"] == "w" and len(out["edges"]) == 1
