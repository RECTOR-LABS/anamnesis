"""POST /api/chat: streams the agent's reply over Server-Sent Events (SSE).

No engine logic lives here — `deps.get_agent()` returns the frozen qwen-agent Assistant
(api/deps.py); this route only drives its `run()` generator and projects each yield onto the
wire as one SSE `data:` frame, followed by a terminal `event: done` frame on success — or, if
the agent raises mid-stream, a terminal `event: error` frame carrying a generic, fixed message
(never the raw exception; see RISK 3 below).

qwen-agent's `run(messages)` contract (introspected against the pinned qwen_agent==0.0.34,
`qwen_agent.llm.schema.Message`): each yield is the CUMULATIVE message list for the turn —
"streaming" means the LAST message's `content` grows across yields, it is not per-token
deltas — and list items may be `Message` pydantic objects or plain dicts, so callers must
normalize both (`.model_dump()` when available, else `dict(...)`). `content` is
`str | list[ContentItem]` (the list form is joined from each item's `.text`; image/file/audio/
video parts carry no text and are dropped — this surface is text-only). `Message.role` is
validated to one of user/assistant/system/function (schema.py's `role_checker` rejects
anything else — there is no "tool" role), so a tool call instead surfaces as either an
ASSISTANT message carrying `function_call: {"name", "arguments"}` (the agent is about to call a
tool) or a FUNCTION-role message carrying `name` (the tool's response) — both are projected
onto an optional `tool` field on the wire payload so a client can render a "used tool X"
affordance without having to know this role/function_call distinction itself.

RISK 2 — blocking sync generator vs. the asyncio event loop: `deps.get_agent().run(...)` does
blocking LLM + forensic-tool I/O (Helius reads via the MCP child). Handing that sync generator
straight to an async `EventSourceResponse` would stall the whole event loop for every other
in-flight request. `iterate_in_threadpool` (the same helper `EventSourceResponse` falls back to
internally for a plain sync iterable) is applied explicitly here so the offload holds regardless
of sse_starlette's internal fallback path; each `next()` call runs on a threadpool thread — one
at a time, so the generator is never entered concurrently — while the event loop stays free.

RISK 3 — a mid-stream agent exception must not silently drop the connection, and must stay
leak-safe: without a guard, an exception raised partway through `get_agent().run(...)` (LLM
timeout, a forensic tool blowing up, ...) would break out of the loop, skip the terminal `done`
frame, and propagate — uvicorn logs the traceback server-side (key-safe, since the engine scrubs
Helius URLs at the source — see `anamnesis.forensic.helius._rpc`), but the client is left with a
truncated stream and no signal the turn failed. `_stream_chat` instead catches any exception from
the loop, emits exactly one terminal `event: error` frame carrying a GENERIC, FIXED message, and
returns (no `done` follows an `error`). The message is deliberately never built from `str(exc)` or
the exception's args/traceback: a raw error surfacing from qwen-agent or the Helius client can
itself carry a key-bearing URL, and echoing it to the client would reopen the exact leak vector
RISK 1 (api/main.py) guards against. Only the exception's class name is logged server-side
(`type(exc).__name__` — never `str(exc)`) for traceability.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterator

from fastapi import APIRouter
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import iterate_in_threadpool

from api import deps

router = APIRouter()


class ChatIn(BaseModel):
    message: str
    mint: str | None = None  # forward-compat only: the agent recalls/investigates via its own
    # tools from the message text, so this is accepted but not otherwise wired in yet.


def _content_text(content: object) -> str:
    """Coerce a Message's `content` (`str | list[ContentItem]`) to plain text for the wire.
    List items may be `ContentItem` objects or plain dicts; only each item's `text` part is
    kept (image/file/audio/video parts are dropped — this surface is text-only)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            item = item.model_dump() if hasattr(item, "model_dump") else item
            text = item.get("text") if isinstance(item, dict) else None
            if text:
                parts.append(text)
        return "".join(parts)
    return "" if content is None else str(content)


def _tool_name(msg: dict) -> str | None:
    """The tool behind this message, if any: an assistant message mid-call carries
    `function_call: {"name", "arguments"}`; a FUNCTION-role message (the tool's response)
    carries `name` directly. Returns None for a plain user/assistant/system message."""
    function_call = msg.get("function_call")
    if function_call:
        name = (
            function_call.get("name")
            if isinstance(function_call, dict)
            else getattr(function_call, "name", None)
        )
        if name:
            return name
    if msg.get("role") == "function":
        return msg.get("name")
    return None


def _serialize(messages: list) -> dict:
    """Project one `run()` yield (the cumulative message list for the turn) to the wire shape.
    The LAST message is the current state of the turn — growing assistant text, or a tool
    call/response in flight — normalized whether qwen-agent yielded `Message` objects or plain
    dicts."""
    last = messages[-1]
    msg = last.model_dump() if hasattr(last, "model_dump") else dict(last)
    out = {"role": msg.get("role"), "content": _content_text(msg.get("content"))}
    tool = _tool_name(msg)
    if tool:
        out["tool"] = tool
    return out


def _stream_chat(message: str) -> Iterator[dict]:
    """SYNC generator driving the agent turn. Wrapped in `iterate_in_threadpool` (RISK 2, see
    module docstring) before being handed to `EventSourceResponse` — never iterated directly on
    the event loop.

    Empty yields are skipped (`if not chunk: continue`) before indexing the last message in
    `_serialize` — qwen-agent's yields are normally non-empty, but this removes the sharp edge
    of an `IndexError` on an empty list.

    Mid-stream exceptions are caught (RISK 3, see module docstring): on failure this emits one
    generic `event: error` frame and returns without emitting `done` — `error` is itself the
    terminal signal for the failed-turn path, so happy-path `done` must never also follow it.
    """
    messages = [{"role": "user", "content": message}]
    try:
        for chunk in deps.get_agent().run(messages):
            if not chunk:
                continue
            yield {"data": json.dumps(_serialize(chunk))}
    except Exception as exc:
        logging.getLogger(__name__).warning("chat stream failed: %s", type(exc).__name__)
        yield {
            "event": "error",
            "data": json.dumps({"message": "chat stream failed — please retry"}),
        }
        return
    yield {"event": "done", "data": ""}


@router.post("/api/chat")
def post_chat(body: ChatIn) -> EventSourceResponse:
    return EventSourceResponse(iterate_in_threadpool(_stream_chat(body.message)))
