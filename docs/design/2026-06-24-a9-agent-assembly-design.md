# A.9 — Agent assembly + WebUI (design)

**Date:** 2026-06-24
**Status:** approved (brainstorm) → plan next
**Depends on:** A.7 (native tools), A.8 (forensic MCP server), `config.py`, `prompts.py`

## Context

Phases A.1–A.8 built every part the agent needs but never assembled them: the pure
forensic core, the bi-temporal memory, the three native tools (`recall`/`remember`/
`assess_risk`, registered via `@register_tool` in `agent/tools.py`), the system instruction
(`prompts.py`), and the Solana forensics MCP stdio server (`mcp/solana_forensics_mcp.py`).

A.9 wires them into a single Qwen-Agent `Assistant` and exposes it through Qwen-Agent's
built-in `WebUI` — the judged chat surface. The wiring shape is fixed by `SPEC.md`
§"Qwen-Agent wiring"; this doc records the structural and robustness decisions around it and
the testing seam, since **CI installs a dependency subset that omits `qwen-agent`** (any module
importing it is skipped there — see memory `anamnesis-ci-installs-fixed-dep-subset`).

The live "ask the agent" / WebUI smoke is **gated on Qwen access (gate #1)** and `.env` is
absent. So A.9 builds and *unit-tests the assembly*; the live smoke is documented and deferred,
never faked.

## Decisions

### D1 — Structure: pure builders + a thin `build_agent()` shell

Mirror the A.7/A.8 pattern (DI'd, unit-tested logic + a thin runtime-coupled adapter), adapted
to the CI constraint. Split `agent.py` into two layers:

- **Pure builders — no `qwen-agent` import, so they run in CI:**
  - `build_llm_cfg(api_key: str) -> dict` — the `llm_cfg`. The key is **injected**, not read from
    env, so the builder is pure and CI tests it with a dummy.
  - `mcp_entrypoint_path() -> Path` — resolves the MCP entrypoint absolutely (see D2).
  - `build_function_list() -> list` — the `mcpServers` spawn block + the native tool names.
- **Thin shell — imports `qwen-agent`, so its test `importorskip`s:**
  - `build_agent() -> Assistant`.

This puts the **typo-prone surface** (model id, base URL, `model_type`, spawn command, entrypoint
path, native tool names) under CI coverage even though `qwen-agent` is absent there. The single-
function alternative would leave that whole config dict untested in CI. (Rejected.)

### D2 — MCP spawn: `sys.executable` + an absolute, fail-fast entrypoint path

The child must run under **the same interpreter** that hosts the agent (it has `anamnesis` +
`mcp` installed via `pip install -e .`), so `command = sys.executable` — never bare `"python"`
(which can resolve to a different interpreter without the deps).

The script path is resolved **absolutely** from the package location rather than left CWD-relative:

```
Path(__file__).resolve().parents[3] / "mcp" / "solana_forensics_mcp.py"
#  agent.py → agent → anamnesis → src → <repo root>; then /mcp/solana_forensics_mcp.py
```

`mcp_entrypoint_path()` **fails fast** with an actionable error if that file is missing, instead
of letting Qwen-Agent spawn a doomed child on first tool call. This holds on ECS because the
deploy preserves the source layout (`git clone` + editable install: `src/` and `mcp/` are
siblings under the repo root). A CWD-relative `["mcp/solana_forensics_mcp.py"]` would break the
moment the WebUI is launched from anywhere other than the repo root — which is why we don't use it,
even though the SPEC snippet wrote it that way. `HELIUS_API_KEY` still flows to the child only
through the inherited process env, never argv (A.8 contract, unchanged).

### D3 — Missing `DASHSCOPE_API_KEY`: `config.require`, fail-fast

`build_agent()` resolves the key via `config.require("DASHSCOPE_API_KEY")` — an actionable
`RuntimeError` ("copy .env.example to .env and fill in DASHSCOPE_API_KEY") — not the SPEC
snippet's bare `os.environ[...]` `KeyError`. This is consistent with the rest of `config.py`.

**Ordering matters:** the `require` call is the *first* line of `build_agent()`, before any
`qwen-agent` import. That makes the missing-key path raise its `RuntimeError` **before** the
`ImportError` that `qwen-agent`'s absence would raise — so the missing-key test runs in CI too.

### D4 — `app.py`: WebUI + demo prompts now

`app.py` launches `WebUI(build_agent(), chatbot_config=...).run()`. Per the approved choice, it
carries demo affordances from the start (the Jul 9 demo depends on them landing fast):

- `prompt.suggestions` — a few starter questions ("Should I ape this token? <mint>", "What do
  you already know about this deployer?"). The concrete **seeded** mint is swapped in by A.10.
- `verbose: True` — surfaces the agent's tool calls (`recall` → `assess_risk` → MCP reads) in the
  UI, making the memory-first, cite-the-evidence reasoning visible — the core demo beat.
- `input.placeholder` — an English placeholder (the qwen-agent default is Chinese).

`app.py` is an entrypoint (not imported by tests); its content is plain configuration data.

## Verified API facts

Probed in the project `.venv` (so the design cites the real API, not memory):

- `qwen-agent` **0.0.34** installed (with `[gui,mcp]`).
- `Assistant(function_list=None, llm=None, system_message='', name=None, description=None,
  files=None, rag_cfg=None)` — our `llm=`, `name=`, `system_message=`, `function_list=` kwargs are
  all valid.
- `WebUI(agent, chatbot_config: Optional[dict] = None)`; `WebUI.run(messages=None, share=False,
  server_name=None, server_port=None, concurrency_limit=10, enable_mention=False, **kwargs)`.
- `chatbot_config` keys the WebUI actually reads: `user.name`, `user.avatar`, `agent.avatar`,
  `input.placeholder`, `prompt.suggestions` (list), `verbose` (bool).

## Architecture

```
app.py  ──▶  WebUI(build_agent(), chatbot_config={prompt.suggestions, verbose, input.placeholder})
                          │
                          ▼
            build_agent() -> Assistant          (agent/agent.py — thin, qwen-agent-coupled)
              1. api_key = config.require("DASHSCOPE_API_KEY")   # actionable, pre-import
              2. from . import tools                             # fires @register_tool
              3. from qwen_agent.agents import Assistant
              4. Assistant(
                   llm           = build_llm_cfg(api_key),       # pure
                   name          = "anamnesis",
                   system_message= SYSTEM_INSTRUCTION,           # prompts.py
                   function_list = build_function_list(),        # pure
                 )
                          │
        ┌─────────────────┴───────────────────────────┐
        ▼                                               ▼
  mcpServers.solana_forensics                    native tools (by name)
   command = sys.executable                       "recall" · "remember" · "assess_risk"
   args    = [<abs>/mcp/solana_forensics_mcp.py]  (resolved from TOOL_REGISTRY once
   (HELIUS_API_KEY via child env)                  agent/tools.py is imported)
```

**The registration subtlety (step 2):** Qwen-Agent resolves the *string* tool names
`"recall"`/`"remember"`/`"assess_risk"` against its global `TOOL_REGISTRY`, which is populated by
the `@register_tool` decorators in `agent/tools.py`. If that module is never imported, the names
don't resolve. `build_agent()` imports it explicitly (`from . import tools`) before constructing
the `Assistant`. (Native-tool order follows SPEC — `recall, remember, assess_risk`; order is
functionally irrelevant since resolution is by name.)

## Testing

`tests/test_agent_assembly.py`:

- **CI-runnable (no `qwen-agent` import):**
  - `build_llm_cfg("dummy")` returns exactly `{model: config.QWEN_MODEL, model_server:
    config.DASHSCOPE_BASE_URL, api_key: "dummy", model_type: "oai", generate_cfg: {top_p: 0.8}}`.
  - `build_function_list()` → first element's `mcpServers.solana_forensics.command == sys.executable`;
    its `args[0]` is absolute, ends with `mcp/solana_forensics_mcp.py`, and `os.path.isfile` is true;
    the native names `recall, remember, assess_risk` follow.
  - `mcp_entrypoint_path()` resolves to an existing file.
  - missing `DASHSCOPE_API_KEY` (`monkeypatch.delenv`) → `build_agent()` raises `RuntimeError`
    (works in CI because `require` precedes the `qwen-agent` import).
- **`pytest.importorskip("qwen_agent")` (skipped in CI):**
  - with a dummy `DASHSCOPE_API_KEY` set, `build_agent()` returns an `Assistant` named `anamnesis`,
    and `recall`/`remember`/`assess_risk` are present in `TOOL_REGISTRY`.
- **Deferred (documented, not faked):** the live WebUI / "ask the agent" smoke — Qwen gate #1.
  qwen-agent caveat recorded: tools cannot combine with `stream=True` in OpenAI-compatible mode;
  Qwen-Agent's `Assistant` runs that function-calling loop itself, so we set no streaming flag.

## Edge cases / failure modes

- **Key absent** → actionable `RuntimeError` at startup (D3).
- **MCP entrypoint missing / wrong CWD** → fail-fast in `mcp_entrypoint_path()` (D2), not a silent
  dead child.
- **`qwen-agent` absent** (CI/plain env) → only the `importorskip` test skips; pure builders + the
  missing-key path still run.
- **No `from __future__ import annotations`** is added to any `@register_tool`/`@server.tool()`
  module (memory `anamnesis-fastmcp-no-future-annotations`); `agent.py` defines no tools, so the
  rule doesn't bind it, but we keep it out for consistency.

## File manifest

| File | Change |
|------|--------|
| `src/anamnesis/agent/agent.py` | **new** — `build_llm_cfg`, `mcp_entrypoint_path`, `build_function_list`, `build_agent` |
| `app.py` | **new** — `WebUI(build_agent(), chatbot_config=...).run()` |
| `tests/test_agent_assembly.py` | **new** — CI-runnable pure tests + `importorskip` assembly test |

No edits to A.7/A.8 code, `config.py`, or `prompts.py`.

## A.10 forward contract (not built here)

A.10 seeds a known-bad deployer + a fresh token (`scripts/seed_demo.py`) and deploys to ECS +
ApsaraDB. It swaps the concrete seeded mint into `app.py`'s `prompt.suggestions` and runs the
hosted Phase-A DoD (instant HIGH-from-memory flag + the N× latency metric). A.9 guarantees a
ready-to-launch `build_agent()` / `app.py` that honors the A.8 stdio contract.

## Deferred / out of scope

- Live WebUI + agent smoke (Qwen gate #1; `.env` absent).
- A.8b deferred forensic reads (`trace_funding`, `get_deployer_token_history`) — Helius gate #3.
- ECS/ApsaraDB deploy + demo seed — A.10.
