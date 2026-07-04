"""HTTP surface tests for POST /api/chat's SSE stream, via FastAPI's TestClient (no network,
no real qwen-agent — api.deps.get_agent is monkeypatched to a FAKE agent whose `.run()` mirrors
the REAL contract: each yield is the CUMULATIVE message list for the turn, list items are plain
dicts (the real qwen-agent yields `Message` pydantic objects too; both normalize the same way
via `.model_dump()` in api/routes/chat.py — not exercised here since CI installs no qwen-agent),
and a tool call surfaces as either an assistant message carrying `function_call` or a
FUNCTION-role response message carrying `name` (see api/routes/chat.py's module docstring for
the full qwen_agent.llm.schema.Message contract this mirrors).

TestClient's `.post(...)` fully drains an SSE response — EventSourceResponse's
`_stream_response` task finishes once the fake agent's generator is exhausted, which cancels
the ping/disconnect/shutdown-listener tasks via its task group — so `.text` carries the whole
raw `data: ...\r\n\r\n`-framed stream; `_parse_sse` below reconstructs the JSON payloads and
whether a terminal `event: done` line was sent.
"""
import json

from fastapi.testclient import TestClient

from api import deps
from api.main import app

client = TestClient(app)


def _parse_sse(text: str) -> tuple[list[dict], bool]:
    """Reconstruct (json-decoded `data:` payloads, whether an `event: done` line was present)
    from a raw SSE response body. The terminal done frame's own empty `data: ` line is dropped
    (not valid JSON, and not a message payload)."""
    lines = text.splitlines()
    data_lines = [line[len("data: "):] for line in lines if line.startswith("data: ")]
    frames = [json.loads(line) for line in data_lines if line]
    saw_done = any(line == "event: done" for line in lines)
    return frames, saw_done


class FakeAgent:
    """Mirrors the REAL qwen-agent contract: `.run(messages, **kwargs)` yields the cumulative
    message list for the turn (streaming = the last message's content growing across yields)."""

    def run(self, messages, **kwargs):
        yield [{"role": "assistant", "content": "Analyzing the mint"}]
        yield [{"role": "assistant", "content": "Analyzing the mint... HIGH risk from memory"}]


class FakeAgentWithTool:
    """Mirrors a turn that calls a tool: an assistant message carrying `function_call` is
    followed (next yield) by the FUNCTION-role response, then the final assistant answer —
    each yield is still the cumulative list, so only the LAST message of each is new."""

    def run(self, messages, **kwargs):
        yield [
            {
                "role": "assistant",
                "content": "",
                "function_call": {"name": "assess_risk", "arguments": "{}"},
            },
        ]
        yield [
            {
                "role": "assistant",
                "content": "",
                "function_call": {"name": "assess_risk", "arguments": "{}"},
            },
            {"role": "function", "name": "assess_risk", "content": '{"level": "high"}'},
        ]
        yield [
            {
                "role": "assistant",
                "content": "",
                "function_call": {"name": "assess_risk", "arguments": "{}"},
            },
            {"role": "function", "name": "assess_risk", "content": '{"level": "high"}'},
            {"role": "assistant", "content": "This mint looks HIGH risk based on memory."},
        ]


class FakeAgentRaisesMidStream:
    """Mirrors a turn that yields one normal chunk, then blows up (LLM timeout, a forensic tool
    erroring, ...) partway through. The exception text deliberately embeds a fake Helius
    api-key-bearing URL to prove the route's error frame never echoes `str(exc)` back to the
    client (RISK 3 in api/routes/chat.py) — only a generic, fixed message may cross the wire."""

    def run(self, messages, **kwargs):
        yield [{"role": "assistant", "content": "Checking the mint..."}]
        raise RuntimeError("boom https://api.helius.xyz/?api-key=SECRET")


class StubMessage:
    """Stands in for a real `qwen_agent.llm.schema.Message` pydantic object: has a
    `.model_dump()` method (unlike a plain dict), so _serialize's `hasattr(last, "model_dump")`
    branch is actually exercised here rather than merely assumed to work — every other fake in
    this file yields plain dicts."""

    def __init__(self, dumped: dict):
        self._dumped = dumped

    def model_dump(self):
        return self._dumped


class FakeAgentYieldsMessageObject:
    """Yields a Message-shaped OBJECT (not a dict) whose `content` is a ContentItem-style list —
    exercises both the `.model_dump()` branch in _serialize and the list-join branch in
    _content_text in the same turn."""

    def run(self, messages, **kwargs):
        yield [
            StubMessage(
                {
                    "role": "assistant",
                    "content": [{"text": "HIGH"}, {"text": " risk"}],
                }
            )
        ]


class StubFunctionCall:
    """A `function_call` value that is itself an OBJECT, not a dict — exercises _tool_name's
    `getattr(function_call, "name", None)` fallback branch, which every other fake's plain-dict
    `function_call` never reaches."""

    def __init__(self, name: str):
        self.name = name


class FakeAgentYieldsFunctionCallObject:
    """Yields a plain-dict message whose `function_call` is a StubFunctionCall object rather
    than a dict, so tool-name extraction is exercised against an object, not just a dict."""

    def run(self, messages, **kwargs):
        yield [
            {
                "role": "assistant",
                "content": "",
                "function_call": StubFunctionCall("assess_risk"),
            }
        ]


class FakeAgentYieldsEmptyListThenNormal:
    """Yields an empty list first (qwen-agent's yields are normally non-empty, but nothing
    forbids it) then a normal chunk — proves the empty-yield guard in _stream_chat skips it
    without an IndexError, and the real chunk still streams through afterward."""

    def run(self, messages, **kwargs):
        yield []
        yield [{"role": "assistant", "content": "Analyzing the mint"}]


def test_post_chat_streams_at_least_two_frames_then_done(monkeypatch):
    monkeypatch.setattr(deps, "get_agent", lambda: FakeAgent())

    resp = client.post("/api/chat", json={"message": "is this a rug?"})

    assert resp.status_code == 200
    frames, saw_done = _parse_sse(resp.text)
    assert len(frames) >= 2
    assert saw_done


def test_post_chat_frame_content_matches_fake_agent_yields(monkeypatch):
    # Proves real serialization (role/content projected from the fake's actual yields), not
    # just frame count.
    monkeypatch.setattr(deps, "get_agent", lambda: FakeAgent())

    resp = client.post("/api/chat", json={"message": "is this a rug?"})

    frames, saw_done = _parse_sse(resp.text)
    assert frames == [
        {"role": "assistant", "content": "Analyzing the mint"},
        {"role": "assistant", "content": "Analyzing the mint... HIGH risk from memory"},
    ]
    assert saw_done


def test_post_chat_surfaces_tool_name_from_function_call_and_function_response(monkeypatch):
    # Message.role has no "tool" literal in qwen-agent's schema (user/assistant/system/function
    # only) — a tool call/response is instead recognized via `function_call` (on an assistant
    # message) or `name` (on a function-role message), and both project onto the wire `tool`
    # field so a client need not know that distinction itself.
    monkeypatch.setattr(deps, "get_agent", lambda: FakeAgentWithTool())

    resp = client.post("/api/chat", json={"message": "is this a rug?"})

    frames, saw_done = _parse_sse(resp.text)
    assert frames == [
        {"role": "assistant", "content": "", "tool": "assess_risk"},
        {"role": "function", "content": '{"level": "high"}', "tool": "assess_risk"},
        {"role": "assistant", "content": "This mint looks HIGH risk based on memory."},
    ]
    assert saw_done


def test_post_chat_missing_message_is_422():
    # No monkeypatch: a missing `message` must fail pydantic validation before the route body
    # (and therefore deps.get_agent / the real agent) ever runs.
    resp = client.post("/api/chat", json={})

    assert resp.status_code == 422


def test_post_chat_midstream_exception_emits_generic_error_frame_not_raw_exception(monkeypatch):
    # The Important finding this locks down: a mid-stream agent exception must not silently drop
    # the connection (no truncated stream / propagated exception reaching the client), and the
    # error frame it emits instead must never leak the raw exception text — which, in a real
    # failure, could itself carry a Helius key-bearing URL.
    monkeypatch.setattr(deps, "get_agent", lambda: FakeAgentRaisesMidStream())

    resp = client.post("/api/chat", json={"message": "is this a rug?"})

    assert resp.status_code == 200
    text = resp.text
    # Leak-safety: none of the raw exception's text reaches the wire.
    assert "SECRET" not in text
    assert "api-key" not in text
    assert "boom" not in text
    # The generic error frame is present, with the fixed message, and no `done` follows it.
    assert "event: error" in text
    frames, saw_done = _parse_sse(text)
    assert frames == [
        {"role": "assistant", "content": "Checking the mint..."},
        {"message": "chat stream failed — please retry"},
    ]
    assert not saw_done


def test_post_chat_serializes_message_object_with_model_dump_and_content_list(monkeypatch):
    # Closes a coverage gap: every other fake in this file yields plain dicts, so _serialize's
    # `.model_dump()` branch (taken for real qwen-agent Message objects) was never actually
    # exercised until now.
    monkeypatch.setattr(deps, "get_agent", lambda: FakeAgentYieldsMessageObject())

    resp = client.post("/api/chat", json={"message": "is this a rug?"})

    frames, saw_done = _parse_sse(resp.text)
    assert frames == [{"role": "assistant", "content": "HIGH risk"}]
    assert saw_done


def test_post_chat_extracts_tool_name_from_function_call_object_not_only_dict(monkeypatch):
    # _tool_name's object branch (`getattr(function_call, "name", None)`) is only reached when
    # function_call isn't a dict; every other test's function_call is a plain dict, so this locks
    # down the object path too.
    monkeypatch.setattr(deps, "get_agent", lambda: FakeAgentYieldsFunctionCallObject())

    resp = client.post("/api/chat", json={"message": "is this a rug?"})

    frames, saw_done = _parse_sse(resp.text)
    assert frames == [{"role": "assistant", "content": "", "tool": "assess_risk"}]
    assert saw_done


def test_post_chat_skips_empty_yielded_list_without_crashing(monkeypatch):
    # Minor hardening: an empty yielded list must not reach messages[-1] (IndexError). qwen-agent
    # yields are normally non-empty, but this removes the sharp edge.
    monkeypatch.setattr(deps, "get_agent", lambda: FakeAgentYieldsEmptyListThenNormal())

    resp = client.post("/api/chat", json={"message": "is this a rug?"})

    assert resp.status_code == 200
    frames, saw_done = _parse_sse(resp.text)
    assert frames == [{"role": "assistant", "content": "Analyzing the mint"}]
    assert saw_done
