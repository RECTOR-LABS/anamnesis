# A.8 — Solana Forensics MCP Server (design)

- **Date:** 2026-06-24
- **Status:** Approved — ready for implementation plan
- **Task:** PLAN.md A.8 (`mcp/solana_forensics_mcp.py`)
- **Depends on:** `forensic/helius.py` (A.5), `forensic/signals.py` (A.1), `config.py`

## Goal

Expose Anamnesis's grounded Solana reads as an **MCP stdio server** so the Qwen-Agent
`Assistant` (A.9) can call them as first-class tools alongside the native
`recall`/`remember`/`assess_risk`. The server is a **thin wrapper** over the already-tested
Python forensic core — it adds a transport, not new forensic logic.

It is spawned by Qwen-Agent as a **child process** over stdio. That child-process seam (the
Velox-analog risk the deploy story is built around) is why the backend targets ECS rather
than a scale-to-zero serverless runtime.

## Decisions

### D1 — Runtime: Python (not Node)

`SPEC.md`'s diagram/wiring/deploy text described a Node `.js` MCP child process; `PLAN.md`
A.8 and `pyproject.toml` (`mcp>=1.2`) describe Python. **We build Python.** It reuses the
tested `helius.py` directly instead of maintaining a parallel JavaScript forensic core, and
the child-process/stdio nature — hence the ECS-over-FunctionCompute rationale — is identical
for a Python child. `SPEC.md`'s Node references are corrected as part of this task (see
[Doc reconciliation](#doc-reconciliation)).

### D2 — Scope: 3 thin-wrapper tools now, 2 forensic algorithms deferred

The original 5-tool surface (`get_token_profile`, `get_deployer`, `trace_funding`,
`get_holders`, `get_deployer_token_history`) splits cleanly:

| Tool | Backing today | Ship in A.8? |
|------|---------------|--------------|
| `get_token_profile` | `build_token_profile` | ✅ |
| `get_deployer` | `resolve_origin` | ✅ |
| `get_holders` | `get_token_largest_accounts` + `holder_count` + `top_holder_pct` | ✅ |
| `trace_funding` | — (none) | ⏸ deferred |
| `get_deployer_token_history` | — (none; old `getAssetsByCreator` path abandoned) | ⏸ deferred |

`trace_funding` and `get_deployer_token_history` are **new forensic algorithms**, not
wrappers: the former needs a curated CEX/bridge/mixer address set + funding-source
classification; the latter needs an on-chain mint-creation scan. Their correct shape cannot
be validated until live Helius access (gate #3) opens. Shipping unvalidated funding/cluster
logic in a forensic, audited product is a correctness risk we decline. They become their own
tracked task. The compounding-memory demo does not depend on them (deployer prior-rug history
comes from the bi-temporal memory store, not a live read).

### D3 — Structure: testable handler layer + thin entrypoint

Mirror the A.7 pattern (validated in PR #6): the logic lives in a dependency-injected,
unit-tested module inside the package; the runtime-coupled entrypoint is a thin adapter.

- **`src/anamnesis/forensic/mcp_tools.py`** — pure-over-client handler functions
  `(client: HeliusClient, mint: str) -> dict`. Unit-tested with `respx`. **Owns error
  mapping** (so the error path is covered without the MCP runtime).
- **`mcp/solana_forensics_mcp.py`** — `FastMCP` stdio entrypoint. Each `@mcp.tool()` is a
  trivial wrapper: get the shared `HeliusClient`, call the handler, return its dict.

## Verified API facts

Probed in the project venv (so the spec cites a real API, not memory):

- `mcp` distribution **1.12.4** (satisfies `mcp>=1.2`).
- `from mcp.server.fastmcp import FastMCP` is available.
- `FastMCP.run(transport: Literal['stdio','sse','streamable-http'] = 'stdio')` — **synchronous**,
  stdio by default. Ideal for `python mcp/solana_forensics_mcp.py`.
- `FastMCP.tool(name=None, title=None, description=None, ...)` derives each tool's input
  schema from the function's type hints + docstring.

## Architecture

```
Qwen-Agent (A.9)
   │  spawns child:  command=<venv python>  args=["mcp/solana_forensics_mcp.py"]
   │  HELIUS_API_KEY inherited via child env (never argv)
   ▼
mcp/solana_forensics_mcp.py              ← thin entrypoint (I/O, smoke DoD)
   server = FastMCP("solana-forensics")
   @server.tool() get_token_profile / get_deployer / get_holders
   lazy module-level HeliusClient singleton (from config.require)
   server.run()   # stdio (instance named `server`, not `mcp`, to avoid shadowing the package)
   │
   ▼  calls
src/anamnesis/forensic/mcp_tools.py      ← handler layer (PURE-over-client, UNIT-TESTED)
   token_profile_dict(client, mint) -> dict
   deployer_dict(client, mint)      -> dict
   holders_dict(client, mint, *, top_n=10) -> dict
   (each maps HeliusError/httpx errors -> {"error", "mint"})
   │
   ▼  reuses unchanged
src/anamnesis/forensic/helius.py         ← tested A.5 client + extractors
```

## Tool I/O contracts

All addresses are base58 strings. `null` (Python `None`) means "renounced" for authorities
and "unresolved" for a deployer.

### `get_token_profile(mint) -> dict`
Serialized `TokenProfile` (all eight fields), from `build_token_profile`:
```json
{
  "mint": "…", "deployer": "…|null", "created_at": "ISO-8601|null",
  "mint_authority": "…|null", "freeze_authority": "…|null",
  "lp_secured": false, "top_holder_pct": 0.0, "holder_count": 0
}
```

### `get_deployer(mint) -> dict`
Cheapest single-purpose read for the memory key, from `resolve_origin`:
```json
{ "mint": "…", "deployer": "…|null", "created_at": "ISO-8601|null" }
```
`deployer` is `null` when the creation tx is unresolvable **or** the only fallback is a known
launchpad shared authority (`LAUNCHPAD_AUTHORITIES`) — never a false cluster anchor.

### `get_holders(mint, top_n=10) -> dict`
Holder concentration detail (composes `get_asset` for supply + `get_token_largest_accounts`
+ `holder_count`):
```json
{
  "mint": "…", "holder_count": 0, "top_holder_pct": 0.0,
  "largest": [ { "address": "…", "amount": "…" } ]
}
```
`top_holder_pct` is the same metric `build_token_profile` uses (largest account ÷ supply);
no new concentration logic is introduced. `largest` is truncated to `top_n`.

### Error result (any tool)
Expected upstream failures return a structured, LLM-readable result instead of crashing the
stdio loop:
```json
{ "error": "<clean message>", "mint": "…" }
```
Produced by catching `HeliusError` and `httpx.HTTPError` in the handler layer. Unexpected
exceptions propagate to FastMCP's own `isError` handling.

## Configuration & secrets

- `HELIUS_API_KEY` is read once via `config.require("HELIUS_API_KEY")` when the singleton
  `HeliusClient` is first built. Missing → fail fast with the existing actionable message.
- The key reaches the child **only** through inherited process env (A.9 sets it on the
  spawned process), never argv, never committed — per Global Constraints.
- The entrypoint relies on the editable-installed `anamnesis` package being importable in the
  spawning interpreter (it is, via `pip install -e .`).

## Testing & DoD

Per PLAN's testability boundary, `mcp/` is I/O-bound (smoke DoD) — but the handler layer is
I/O-free under a mocked client, so it gets real unit coverage:

- **`tests/test_mcp_tools.py` (unit, `respx`)** — mock the Helius JSON-RPC; assert:
  - `token_profile_dict` for a renounced fixture and an active-authority fixture (exact dict).
  - `deployer_dict` resolves deployer + `created_at`; `null` on an unresolvable/launchpad case.
  - `holders_dict` shape: `holder_count`, `top_holder_pct`, `largest` truncated to `top_n`.
  - error mapping: a Helius error payload → `{"error", "mint"}`.
- **Registration smoke** — import `mcp/solana_forensics_mcp.py` (via `importlib` from path,
  guarded like `test_agent_tool_registration.py`'s `importorskip`) and assert the three tools
  register on the `FastMCP` instance. Skips cleanly where `mcp` is absent (CI installs a
  pinned subset).
- **Live stdio smoke — deferred to Helius gate #3** (`.env` absent today): run the server,
  list tools, call `get_token_profile` for a real mint, confirm a populated profile. Tracked,
  not silently skipped.
- `ruff`-clean; type hints on public functions; 4-space indent.

## Doc reconciliation (part of this task)

- **`SPEC.md`** — replace Node references: the `mcpServers` wiring `command: "<project venv python>"` /
  `args: ["mcp/solana_forensics_mcp.py"]`; architecture diagram + deploy narrative say
  "Python forensic-MCP child process"; the toolset line reflects the honest 3-now / 2-deferred
  split.
- **`PLAN.md`** A.8 — Python entrypoint, the three shipped tools, and the two deferred reads
  carved into a tracked follow-on task (`trace_funding`, `get_deployer_token_history`).

## Deferred scope (explicit, tracked)

`trace_funding` and `get_deployer_token_history` — own forensic task. Requires: a curated
funding-source (CEX/bridge/mixer) address set; an on-chain mint-creation scan over the
deployer's signatures (or a validated `getAssetsByAuthority`/`getAssetsByCreator` path); and
live Helius (#3) to confirm tx shapes before the logic is trusted. Out of A.8.

## A.9 integration contract (forward-looking, not built here)

A.9's `function_list` gains an `mcpServers` block:
```python
{"mcpServers": {"solana_forensics": {
    "command": "<venv python>",
    "args": ["mcp/solana_forensics_mcp.py"],
    # HELIUS_API_KEY flows via the child process env, never argv.
}}}
```
plus the native `["recall", "remember", "assess_risk"]`. A.8 only guarantees the entrypoint
honors this contract (stdio, env-keyed, three tools).

## File manifest

| File | Change |
|------|--------|
| `src/anamnesis/forensic/mcp_tools.py` | **new** — 3 handler functions + error mapping |
| `mcp/solana_forensics_mcp.py` | **new** — FastMCP stdio entrypoint |
| `tests/test_mcp_tools.py` | **new** — respx unit tests + registration smoke |
| `SPEC.md` | edit — Node→Python; honest toolset split |
| `PLAN.md` | edit — A.8 Python + 3 tools; deferred follow-on task |
