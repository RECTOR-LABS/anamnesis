# A.8 Solana Forensics MCP Server — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose Anamnesis's grounded Solana reads as an MCP stdio server (3 thin-wrapper tools) so the Qwen-Agent Assistant can call them alongside the native memory tools.

**Architecture:** A dependency-injected, unit-tested handler layer (`src/anamnesis/forensic/mcp_tools.py`) composes the tested `helius.py` reads into JSON-able dicts and maps upstream errors to a structured result. A thin `FastMCP` stdio entrypoint (`mcp/solana_forensics_mcp.py`) owns a lazy `HeliusClient` singleton and registers three tools over those handlers. Mirrors the A.7 pattern (testable core + thin runtime adapter).

**Tech Stack:** Python 3.12 · `mcp` 1.12.4 (`FastMCP`, stdio) · `httpx` · the existing `forensic/helius.py` · `pytest` + `respx`/fakes · `ruff`.

**Design doc:** `docs/design/2026-06-24-a8-mcp-server.md`.

## Global Constraints

*Every task's requirements implicitly include this section. Values copied from PLAN.md / the design doc.*

- **Python style:** 4-space indent, PEP8, `ruff`-clean, type hints on public functions, comments only for non-obvious logic.
- **Secrets via env only:** `HELIUS_API_KEY` read via `config.require(...)`, never argv/committed.
- **Read-only on-chain** — no signing/trading/mutating.
- **`mcp` is absent in CI** (CI installs a pinned pip subset): any test that imports the `mcp` package or the FastMCP entrypoint MUST guard with `pytest.importorskip("mcp")`. Handler tests must NOT import `mcp`, so they run in CI.
- **Commits:** GPG-signed (`git commit -S`) as RECTOR, **ZERO AI attribution** (no `Co-Authored-By`, no "Generated with").
- **Branch:** `feat/a8-mcp-server` (already created; design + this plan already committed on it).

## File Structure

| File | Responsibility |
|------|----------------|
| `src/anamnesis/forensic/mcp_tools.py` | **new** — 3 handler functions `(client, mint) -> dict` + error mapping. The unit-tested surface. |
| `tests/test_mcp_tools.py` | **new** — handler tests via a canned fake client (runs in CI; no `mcp`, no network). |
| `mcp/solana_forensics_mcp.py` | **new** — `FastMCP` stdio entrypoint: lazy `HeliusClient`, 3 `@server.tool()` wrappers, `server.run()`. |
| `tests/test_mcp_server_registration.py` | **new** — registration smoke (loads the entrypoint; `importorskip("mcp")`; skipped in CI). |
| `SPEC.md` | **modify** — Node→Python wiring/deploy; honest 3+2 toolset. |
| `PLAN.md` | **modify** — A.8 = 3 Python tools; the 2 deferred reads as a tracked follow-on. |

---

### Task 1: Forensic MCP tool handlers (PURE over injected client, TDD)

**Files:**
- Create: `src/anamnesis/forensic/mcp_tools.py`
- Test: `tests/test_mcp_tools.py`

**Interfaces:**
- Consumes (from `anamnesis.forensic.helius`): `HeliusClient`, `HeliusError`, `build_token_profile(client, mint) -> TokenProfile`, `resolve_origin(client, mint) -> tuple[str|None, str|None]`, `holder_count(client, mint) -> int`, `top_holder_pct(largest: list[dict], supply: int) -> float`.
- Produces: `token_profile_dict(client: HeliusClient, mint: str) -> dict`, `deployer_dict(client: HeliusClient, mint: str) -> dict`, `holders_dict(client: HeliusClient, mint: str, *, top_n: int = 10) -> dict`. On a caught `HeliusError`/`httpx.HTTPError`, each returns `{"error": str, "mint": str}`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_mcp_tools.py`:

```python
"""Unit tests for the A.8 forensic MCP tool handlers — pure over an injected client.

Mirrors test_helius.py's _FakeClient approach (order-independent canned reads) so the
multi-call composition + serialization are tested without network or the mcp package;
these run in CI. Raising fakes cover the error-mapping path.
"""
from __future__ import annotations

import httpx

from anamnesis.forensic.helius import HeliusError
from anamnesis.forensic.mcp_tools import deployer_dict, holders_dict, token_profile_dict


class _FakeClient:
    """Canned, order-independent forensic reads: active mint authority, one big holder."""

    def get_asset(self, mint: str) -> dict:
        return {
            "token_info": {"supply": 1000, "mint_authority": "deployerW", "freeze_authority": None},
            "authorities": [{"address": "deployerW", "scopes": ["full"]}],
        }

    def get_token_largest_accounts(self, mint: str) -> list[dict]:
        return [{"address": "acc1", "amount": "300"}, {"address": "acc2", "amount": "50"}]

    def oldest_signature(self, mint: str, **_: object) -> str | None:
        return "deploySig"

    def get_transaction(self, signature: str) -> dict:
        return {"blockTime": 1700000000,
                "transaction": {"message": {"accountKeys": [{"pubkey": "deployerW"}]}}}

    def get_token_accounts(self, mint: str, **_: object) -> dict:
        return {"total": 742}


def test_token_profile_dict_serializes_all_fields():
    out = token_profile_dict(_FakeClient(), "mintA")
    assert out == {
        "mint": "mintA",
        "deployer": "deployerW",
        "created_at": "2023-11-14T22:13:20+00:00",
        "mint_authority": "deployerW",
        "freeze_authority": None,
        "lp_secured": False,
        "top_holder_pct": 30.0,
        "holder_count": 742,
    }


def test_deployer_dict_returns_deployer_and_created_at():
    out = deployer_dict(_FakeClient(), "mintA")
    assert out == {"mint": "mintA", "deployer": "deployerW",
                   "created_at": "2023-11-14T22:13:20+00:00"}


def test_holders_dict_reports_concentration_and_truncates():
    out = holders_dict(_FakeClient(), "mintA", top_n=1)
    assert out["mint"] == "mintA"
    assert out["holder_count"] == 742
    assert out["top_holder_pct"] == 30.0                       # 300 / 1000
    assert out["largest"] == [{"address": "acc1", "amount": "300"}]   # truncated to top_n=1


class _HeliusRaisingClient(_FakeClient):
    def get_asset(self, mint: str) -> dict:
        raise HeliusError("getAsset failed: boom")


class _HttpxRaisingClient(_FakeClient):
    def get_asset(self, mint: str) -> dict:
        raise httpx.HTTPError("network down")


def test_handlers_map_upstream_errors_to_structured_result():
    # token_profile_dict + holders_dict both open with get_asset -> clean degradation.
    assert token_profile_dict(_HeliusRaisingClient(), "mintA") == {
        "error": "getAsset failed: boom", "mint": "mintA"}
    assert holders_dict(_HeliusRaisingClient(), "mintA") == {
        "error": "getAsset failed: boom", "mint": "mintA"}
    assert token_profile_dict(_HttpxRaisingClient(), "mintA") == {
        "error": "network down", "mint": "mintA"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_mcp_tools.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'anamnesis.forensic.mcp_tools'`.

- [ ] **Step 3: Implement the handler layer**

Create `src/anamnesis/forensic/mcp_tools.py`:

```python
"""Forensic MCP tool handlers (A.8) — pure over an injected HeliusClient.

Each handler composes the tested helius.py reads into a JSON-able dict for the MCP server to
return, and maps expected upstream failures (HeliusError / httpx errors) to a structured
``{"error", "mint"}`` result, so a bad read degrades into an LLM-readable signal instead of
crashing the stdio loop. The client is injected, so these are unit-tested with a canned fake
client — no network, no mcp package — and run in CI. The thin entrypoint
(mcp/solana_forensics_mcp.py) owns the live client.
"""
from __future__ import annotations

import httpx

from .helius import (
    HeliusClient,
    HeliusError,
    build_token_profile,
    holder_count,
    resolve_origin,
    top_holder_pct,
)

_UPSTREAM_ERRORS = (HeliusError, httpx.HTTPError)


def token_profile_dict(client: HeliusClient, mint: str) -> dict:
    """Full forensic profile for a mint (authorities, liquidity, holders, deployer, created_at)."""
    try:
        p = build_token_profile(client, mint)
    except _UPSTREAM_ERRORS as e:
        return {"error": str(e), "mint": mint}
    return {
        "mint": p.mint,
        "deployer": p.deployer,
        "created_at": p.created_at,
        "mint_authority": p.mint_authority,
        "freeze_authority": p.freeze_authority,
        "lp_secured": p.lp_secured,
        "top_holder_pct": p.top_holder_pct,
        "holder_count": p.holder_count,
    }


def deployer_dict(client: HeliusClient, mint: str) -> dict:
    """The mint's deployer wallet (memory key) + creation time; nulls when unresolved."""
    try:
        deployer, created_at = resolve_origin(client, mint)
    except _UPSTREAM_ERRORS as e:
        return {"error": str(e), "mint": mint}
    return {"mint": mint, "deployer": deployer, "created_at": created_at}


def holders_dict(client: HeliusClient, mint: str, *, top_n: int = 10) -> dict:
    """Holder concentration: total holders, top-holder %, and the largest accounts (<= top_n)."""
    try:
        asset = client.get_asset(mint)
        supply = int((asset.get("token_info") or {}).get("supply") or 0)
        largest = client.get_token_largest_accounts(mint)
        count = holder_count(client, mint)
    except _UPSTREAM_ERRORS as e:
        return {"error": str(e), "mint": mint}
    return {
        "mint": mint,
        "holder_count": count,
        "top_holder_pct": top_holder_pct(largest, supply),
        "largest": [
            {"address": a.get("address"), "amount": a.get("amount")} for a in largest[:top_n]
        ],
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_mcp_tools.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Lint**

Run: `.venv/bin/ruff check src/anamnesis/forensic/mcp_tools.py tests/test_mcp_tools.py`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add src/anamnesis/forensic/mcp_tools.py tests/test_mcp_tools.py
git commit -S -m "feat: forensic MCP tool handlers over the tested helius core"
```

---

### Task 2: FastMCP stdio entrypoint + registration smoke

**Files:**
- Create: `mcp/solana_forensics_mcp.py`
- Test: `tests/test_mcp_server_registration.py`

**Interfaces:**
- Consumes: `anamnesis.config.require`, `anamnesis.forensic.helius.HeliusClient`, and Task 1's `token_profile_dict` / `deployer_dict` / `holders_dict`.
- Produces: a module exposing `server: FastMCP` with three registered tools — `get_token_profile(mint)`, `get_deployer(mint)`, `get_holders(mint, top_n=10)` — and a `__main__` guard that calls `server.run()` (stdio). Module load registers the tools without reading env or touching the network (the `HeliusClient` is lazy).

- [ ] **Step 1: Write the failing test**

Create `tests/test_mcp_server_registration.py`:

```python
"""Registration smoke for the A.8 FastMCP entrypoint.

Loads mcp/solana_forensics_mcp.py (which lives outside the importable src/ tree because it is
spawned as a standalone stdio script) and asserts the three forensic tools register on the
FastMCP server. Requires the mcp package — skipped in CI, which installs a pinned subset
without it (mirrors test_agent_tool_registration.py's qwen_agent guard).
"""
from __future__ import annotations

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
    names = {t.name for t in server._tool_manager.list_tools()}
    assert names == {"get_token_profile", "get_deployer", "get_holders"}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/test_mcp_server_registration.py -q`
Expected: FAIL — `spec_from_file_location` finds no file / `exec_module` raises `FileNotFoundError` (entrypoint not created yet). (Locally `mcp` is installed, so the test runs rather than skips.)

- [ ] **Step 3: Implement the entrypoint**

Create `mcp/solana_forensics_mcp.py`:

```python
"""Solana Forensics MCP server (A.8) — a thin FastMCP stdio wrapper over the tested forensic
core. Spawned by the Qwen-Agent Assistant as a child process; exposes three grounded Solana
reads as MCP tools. HELIUS_API_KEY is read from the inherited process env (never argv).

Run standalone (stdio):  python mcp/solana_forensics_mcp.py
"""
from __future__ import annotations

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
        _client = HeliusClient(config.require("HELIUS_API_KEY"))
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/pytest tests/test_mcp_server_registration.py -q`
Expected: PASS (1 test).

- [ ] **Step 5: Lint + full suite (confirm nothing regressed and CI-skip holds)**

Run: `.venv/bin/ruff check mcp/solana_forensics_mcp.py tests/test_mcp_server_registration.py`
Expected: no errors.
Run: `.venv/bin/pytest -q`
Expected: PASS, all green (existing suite + the 5 new tests; registration smoke runs locally because `mcp` is installed).

- [ ] **Step 6: Commit**

```bash
git add mcp/solana_forensics_mcp.py tests/test_mcp_server_registration.py
git commit -S -m "feat: Solana forensics MCP stdio server (3 thin Helius reads)"
```

---

### Task 3: Reconcile SPEC.md and PLAN.md (Node→Python, honest 3+2 toolset)

**Files:**
- Modify: `SPEC.md` (lines ~72-73, ~103-104, ~151)
- Modify: `PLAN.md` (line ~18, Task A.8 at ~566-573, Self-Review at ~625)

**Interfaces:** docs only — no code, no test. Verification is a grep for residual runtime-Node refs. **Do NOT touch** the unrelated graph-"node"/"Nodes" text (SPEC lines 55, 80, 122, 134) or the `.json()` call (PLAN line 197).

- [ ] **Step 1: SPEC.md — toolset line.** Replace the 5-tool block (lines 72-73):

  Old:
  ```
            │     get_token_profile · get_deployer · trace_funding ·
            │     get_holders · get_deployer_token_history
  ```
  New:
  ```
            │     get_token_profile · get_deployer · get_holders
            │     (trace_funding · get_deployer_token_history — deferred: need a
            │      funding-source address set + an on-chain mint-scan + live Helius)
  ```

- [ ] **Step 2: SPEC.md — wiring block.** Replace the Node command (lines 103-104):

  Old:
  ```
              "command": "node",
              "args": ["mcp/solana-forensics-mcp.js"],
  ```
  New:
  ```
              "command": "python",   # the project venv interpreter (sys.executable in code)
              "args": ["mcp/solana_forensics_mcp.py"],
  ```

- [ ] **Step 3: SPEC.md — deploy narrative.** In line 151, replace `the Node forensic-MCP child process` with `the Python forensic-MCP child process`, and `the exact Node-subprocess-in-a-serverless-container seam` with `the exact child-subprocess-in-a-serverless-container seam`.

- [ ] **Step 4: PLAN.md — constraint line.** In line 18, replace `the Node/Python MCP child process is the Velox-style serverless-subprocess risk` with `the Python MCP child process is the Velox-style serverless-subprocess risk`.

- [ ] **Step 5: PLAN.md — rewrite Task A.8 body.** Replace the A.8 block (lines 566-573) with:

  ```markdown
  ### Task A.8: Forensic MCP server (thin wrapper)

  **Files:** Create `mcp/solana_forensics_mcp.py`, `src/anamnesis/forensic/mcp_tools.py`.
  **Design:** `docs/design/2026-06-24-a8-mcp-server.md`.
  **Interfaces — Produces** a Python MCP **stdio** server (FastMCP) exposing three thin reads
  over `forensic/helius.py`: `get_token_profile`, `get_deployer`, `get_holders`. Handlers live
  in `forensic/mcp_tools.py` (DI'd client, unit-tested); the entrypoint is the thin adapter.

  - [ ] **Step 1:** Implement `mcp_tools.py` handlers `(client, mint) -> dict` mapping upstream
    errors to `{"error", "mint"}`; unit-test with a canned fake client (runs in CI).
  - [ ] **Step 2:** Implement `mcp/solana_forensics_mcp.py` with FastMCP (`mcp>=1.2`); lazy
    `HeliusClient` from `HELIUS_API_KEY` (env); `server.run()` (stdio). Registration smoke
    guarded by `importorskip("mcp")`.
  - [ ] **Step 3: Live smoke (deferred to Helius gate #3):** run the server, list tools, call
    `get_token_profile` for a real mint → populated profile.
  - [ ] **Step 4: Commit.** `git commit -S -m "feat: Solana forensics MCP server (wraps Helius)"`

  ### Task A.8b: Funding-trace + deployer-token-history reads (deferred)

  **Blocked on:** Helius access (gate #3) to validate tx shapes before the logic is trusted.
  **Produces** two further MCP tools: `trace_funding` (deployer's funding source via parsed tx
  history → CEX/bridge/mixer, needs a curated address set) and `get_deployer_token_history`
  (on-chain mint-creation scan over the deployer's signatures). New forensic algorithms, not
  wrappers — full TDD + live smoke when access lands.
  ```

- [ ] **Step 6: PLAN.md — Self-Review line.** In line 625, replace `MCP forensic toolset ✓(A.8)` with `MCP forensic toolset ✓(A.8: 3 reads; trace_funding + deployer-history deferred to A.8b)`.

- [ ] **Step 7: Verify no stale runtime-Node refs remain**

Run: `grep -nE '"command": "node"|solana-forensics-mcp\.js|Node forensic-MCP|Node-subprocess' SPEC.md PLAN.md`
Expected: no matches (empty output).

- [ ] **Step 8: Commit**

```bash
git add SPEC.md PLAN.md
git commit -S -m "docs: reconcile SPEC/PLAN to the Python A.8 MCP server (3 reads + A.8b deferred)"
```

---

## Deferred verification (not a task — gated on access)

- **Live stdio smoke** (Helius gate #3 / `.env`): launch `python mcp/solana_forensics_mcp.py`, connect an MCP client, `list_tools`, and call `get_token_profile` for a real mint; confirm a populated profile and that authorities/holders match the chain. Retire the "confirm endpoints Day 1" risk here.
- **A.9 wiring:** the agent's `function_list` spawns this entrypoint via `{"command": <venv python>, "args": ["mcp/solana_forensics_mcp.py"]}` with `HELIUS_API_KEY` in the child env. Built in A.9, not here.

## Self-Review

**Spec coverage** (against `docs/design/2026-06-24-a8-mcp-server.md`):
- D1 Python runtime → Task 2 entrypoint + Task 3 doc reconciliation. ✓
- D2 scope (3 now / 2 deferred) → Tasks 1-2 ship 3; Task 3 Step 5 records A.8b. ✓
- D3 handler layer + thin entrypoint → Task 1 / Task 2. ✓
- Tool I/O contracts → Task 1 tests assert exact dict shapes; error result asserted. ✓
- Config/secrets (env-only, lazy) → Task 2 `_helius()`. ✓
- Testing/DoD (handler units run in CI; registration smoke `importorskip`; live smoke deferred) → Tasks 1-2 + Deferred section. ✓
- Doc reconciliation → Task 3. ✓

**Placeholder scan:** No TBD/TODO; every code + edit step carries complete content. Deferred items (A.8b, live smoke) are explicit scope with concrete prerequisites, not vague "later." ✓

**Type consistency:** `token_profile_dict` / `deployer_dict` / `holders_dict` signatures identical in the Interfaces blocks, the test imports, the implementation, and the entrypoint calls. `resolve_origin` returns `(deployer, created_at)` consumed as a 2-tuple in `deployer_dict`. `top_holder_pct(largest, supply)` and `holder_count(client, mint)` match `helius.py`. `server._tool_manager.list_tools()[].name` verified against `mcp` 1.12.4. ✓
