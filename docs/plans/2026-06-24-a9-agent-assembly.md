# A.9 — Agent assembly + WebUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Assemble the merged A.1–A.8 pieces into one Qwen-Agent `Assistant` (`build_agent()`) and launch it through Qwen-Agent's built-in `WebUI` (`app.py`).

**Architecture:** Two layers in `src/anamnesis/agent/agent.py` — pure, CI-tested config builders (`build_llm_cfg`, `mcp_entrypoint_path`, `build_function_list`) and a thin, qwen-agent-coupled `build_agent()` shell. `app.py` is a minimal root-level entrypoint carrying demo affordances. The forensic MCP server (A.8) is wired as a stdio child spawned under `sys.executable`; the native memory tools (A.7) are wired by name.

**Tech Stack:** Python 3.12, qwen-agent 0.0.34 (`[gui,mcp]`, installed in `.venv`), `mcp` 1.12.4, FastMCP, pytest, ruff.

## Global Constraints

Every task's requirements implicitly include these (verbatim from SPEC/handoff/memory):

- **Commits:** GPG-signed (`git commit -S`), authored as RECTOR (key `BF47B9DC1FA320FA`). **ZERO AI attribution** — no `Co-Authored-By`, no "Generated with", anywhere (commits/PRs/docs).
- **Branch/PR:** all work on `feat/a9-agent-assembly` (already checked out); conventional commits; one PR; `gh pr merge --merge --delete-branch` after CI green (delete local + remote).
- **TDD:** failing test → run-red → minimal impl → run-green → ruff → commit.
- **CI omits `qwen-agent` + `mcp` + `openai`.** Any test importing them MUST guard with `pytest.importorskip(...)` so it skips in CI. Put the guard *inside the test function*, never at module top, or it skips sibling CI-runnable tests too. (Memory: `anamnesis-ci-installs-fixed-dep-subset`.)
- **NEVER add `from __future__ import annotations`** to any module defining `@register_tool`/`@server.tool()` functions (Memory: `anamnesis-fastmcp-no-future-annotations`). `agent.py` and `app.py` define neither, so we simply omit it (no need for it under py312).
- **Tools cannot combine with `stream=True`** in OpenAI-compatible mode. Qwen-Agent's `Assistant` runs its own function-calling loop, so we set no streaming flag.
- **Docs** live in `docs/design/` + `docs/plans/` — NOT `docs/superpowers/`.
- **Ruff:** default rule set (E + F; no isort `I`), `line-length = 100`, `target-version = "py312"`.
- **Verify like CI before pushing:** `.venv/bin/ruff check .` · `.venv/bin/pytest -q` · `.venv/bin/pytest -q --store=mongo`.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `src/anamnesis/agent/agent.py` | **new** — pure config builders + thin `build_agent()` |
| `app.py` | **new** — root-level WebUI entrypoint + `CHATBOT_CONFIG` demo data |
| `tests/test_agent_assembly.py` | **new** — CI-runnable builder + missing-key tests; `importorskip` assembly test |
| `tests/test_app_entrypoint.py` | **new** — CI-runnable `CHATBOT_CONFIG` + `main` checks (loads `app.py` by path) |

No edits to A.7/A.8 code, `config.py`, or `prompts.py`.

---

### Task 1: Pure config builders

**Files:**
- Create: `src/anamnesis/agent/agent.py`
- Test: `tests/test_agent_assembly.py`

**Interfaces:**
- Consumes: `anamnesis.config.QWEN_MODEL`, `anamnesis.config.DASHSCOPE_BASE_URL` (existing).
- Produces:
  - `NATIVE_TOOLS: list[str]` == `["recall", "remember", "assess_risk"]`
  - `build_llm_cfg(api_key: str) -> dict`
  - `mcp_entrypoint_path() -> pathlib.Path` (absolute; raises `RuntimeError` if missing)
  - `build_function_list() -> list` (first element the `mcpServers` dict, then the native names)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_agent_assembly.py`:

```python
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
    fl = build_function_list()
    block = fl[0]["mcpServers"]["solana_forensics"]
    assert block["command"] == sys.executable
    assert len(block["args"]) == 1
    arg = block["args"][0]
    assert os.path.isabs(arg)
    assert os.path.isfile(arg)
    assert arg.endswith(os.path.join("mcp", "solana_forensics_mcp.py"))
    assert fl[1:] == ["recall", "remember", "assess_risk"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_agent_assembly.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'anamnesis.agent.agent'`.

- [ ] **Step 3: Write the minimal implementation**

Create `src/anamnesis/agent/agent.py`:

```python
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


def build_function_list() -> list:
    """The Assistant's function_list: the forensic MCP server (spawned as a stdio child under
    this same interpreter, so it has anamnesis + mcp installed) plus the native memory tools by
    name. HELIUS_API_KEY reaches the child only through its inherited env, never argv."""
    return [
        {
            "mcpServers": {
                "solana_forensics": {
                    "command": sys.executable,
                    "args": [str(mcp_entrypoint_path())],
                }
            }
        },
        *NATIVE_TOOLS,
    ]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_agent_assembly.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Lint**

Run: `.venv/bin/ruff check src/anamnesis/agent/agent.py tests/test_agent_assembly.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add src/anamnesis/agent/agent.py tests/test_agent_assembly.py
git commit -S -m "feat: A.9 pure agent-config builders (llm_cfg, mcp spawn, function_list)"
```

---

### Task 2: `build_agent()` thin shell

**Files:**
- Modify: `src/anamnesis/agent/agent.py` (append `build_agent`)
- Test: `tests/test_agent_assembly.py` (append two tests)

**Interfaces:**
- Consumes: `build_llm_cfg`, `build_function_list` (Task 1); `anamnesis.config.require`; `anamnesis.agent.tools` (A.7, registers `recall`/`remember`/`assess_risk`); `anamnesis.agent.prompts.SYSTEM_INSTRUCTION` (A.7); `qwen_agent.agents.Assistant`.
- Produces: `build_agent() -> qwen_agent.agents.Assistant` named `"anamnesis"` whose `function_map` contains the 3 native tools + the 3 MCP tools.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_agent_assembly.py`:

```python
def test_build_agent_missing_dashscope_key_raises_actionable_error(monkeypatch):
    # Runs in CI too: config.require() raises BEFORE the qwen-agent import is reached.
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    from anamnesis.agent.agent import build_agent

    with pytest.raises(RuntimeError, match="DASHSCOPE_API_KEY"):
        build_agent()


def test_build_agent_assembles_native_and_mcp_tools(monkeypatch):
    # Real wiring test: constructing the Assistant spawns the MCP stdio child under
    # sys.executable and lists its tools (no HELIUS key needed just to register them).
    # Skipped in CI, which installs neither qwen-agent nor mcp.
    pytest.importorskip("qwen_agent")
    pytest.importorskip("mcp")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dummy-key-for-construction")
    from anamnesis.agent.agent import build_agent

    agent = build_agent()
    assert agent.name == "anamnesis"
    assert {"recall", "remember", "assess_risk"} <= set(agent.function_map)
    assert {"get_token_profile", "get_deployer", "get_holders"} <= set(agent.function_map)
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `.venv/bin/pytest tests/test_agent_assembly.py -q -k build_agent`
Expected: FAIL — `ImportError: cannot import name 'build_agent' from 'anamnesis.agent.agent'`.

- [ ] **Step 3: Write the minimal implementation**

Append to `src/anamnesis/agent/agent.py`:

```python
def build_agent():
    """Assemble the Anamnesis Qwen-Agent Assistant: native memory tools (A.7) + the forensic
    MCP server (A.8), system instruction from prompts.py, qwen-max over DashScope-intl.

    DASHSCOPE_API_KEY is resolved FIRST — before the qwen-agent import — so a missing key
    raises an actionable RuntimeError, and that path stays testable in CI (where qwen-agent is
    absent). Importing anamnesis.agent.tools fires its @register_tool decorators so the native
    tool names resolve against Qwen-Agent's TOOL_REGISTRY before the Assistant is built.
    """
    api_key = config.require("DASHSCOPE_API_KEY")

    from qwen_agent.agents import Assistant

    from . import tools  # noqa: F401 — import populates the @register_tool registry
    from .prompts import SYSTEM_INSTRUCTION

    return Assistant(
        llm=build_llm_cfg(api_key),
        name="anamnesis",
        system_message=SYSTEM_INSTRUCTION,
        function_list=build_function_list(),
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_agent_assembly.py -q`
Expected: PASS — 5 passed locally (the assembly test runs; it spawns the MCP child ~1–2s). In a no-qwen-agent environment it would show `4 passed, 1 skipped`.

- [ ] **Step 5: Lint**

Run: `.venv/bin/ruff check src/anamnesis/agent/agent.py tests/test_agent_assembly.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add src/anamnesis/agent/agent.py tests/test_agent_assembly.py
git commit -S -m "feat: A.9 build_agent() assembles native tools + forensic MCP server"
```

---

### Task 3: `app.py` WebUI entrypoint

**Files:**
- Create: `app.py`
- Test: `tests/test_app_entrypoint.py`

**Interfaces:**
- Consumes: `anamnesis.agent.agent.build_agent` (Task 2); `qwen_agent.gui.WebUI` (deferred into `main()`).
- Produces: module-level `CHATBOT_CONFIG: dict` (keys `prompt.suggestions`, `verbose`, `input.placeholder`) and `main() -> None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_app_entrypoint.py`:

```python
"""CI-runnable checks for the WebUI entrypoint (app.py).

app.py lives at the repo root (outside the importable src/ tree, like the MCP entrypoint), so
it is loaded by file path — mirroring tests/test_mcp_server_registration.py. The WebUI import
is deferred inside app.main(), so loading the module here never requires qwen-agent[gui].
"""
import importlib.util
import pathlib

_APP = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def _load_app():
    spec = importlib.util.spec_from_file_location("anamnesis_app", _APP)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_chatbot_config_carries_demo_affordances():
    app = _load_app()
    cfg = app.CHATBOT_CONFIG
    assert isinstance(cfg["prompt.suggestions"], list) and cfg["prompt.suggestions"]
    assert cfg["verbose"] is True
    assert "Anamnesis" in cfg["input.placeholder"]  # our English placeholder, not the default


def test_main_is_callable():
    app = _load_app()
    assert callable(app.main)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_app_entrypoint.py -q`
Expected: FAIL — `FileNotFoundError`/spec load error: `app.py` does not exist yet.

- [ ] **Step 3: Write the minimal implementation**

Create `app.py`:

```python
"""Anamnesis WebUI entrypoint.

Launches Qwen-Agent's built-in WebUI over build_agent() — the judged chat surface. The WebUI
import is deferred into main() so importing this module (e.g. to verify CHATBOT_CONFIG) does
not require the heavy GUI extra, which CI does not install.

Run locally:  python app.py   (needs DASHSCOPE_API_KEY + HELIUS_API_KEY in the env)
"""
from anamnesis.agent.agent import build_agent

# Demo affordances for the judged WebUI. A.10 swaps the concrete seeded mint into the
# suggestions; verbose surfaces the recall -> assess_risk -> MCP tool calls so the
# memory-first, cite-the-evidence reasoning is visible during the demo.
CHATBOT_CONFIG = {
    "prompt.suggestions": [
        "Should I ape this token? Paste a mint address.",
        "What do you already know about this deployer?",
        "Investigate this mint and cite the evidence behind your verdict.",
    ],
    "verbose": True,
    "input.placeholder": "Ask Anamnesis about a token or its deployer.",
}


def main() -> None:
    from qwen_agent.gui import WebUI

    WebUI(build_agent(), chatbot_config=CHATBOT_CONFIG).run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_app_entrypoint.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Lint**

Run: `.venv/bin/ruff check app.py tests/test_app_entrypoint.py`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_app_entrypoint.py
git commit -S -m "feat: A.9 WebUI entrypoint (app.py) with demo prompts"
```

---

### Task 4: Full verification + PR

**Files:** none (verification + integration).

- [ ] **Step 1: Run the full suite exactly as CI does (default store)**

Run: `.venv/bin/pytest -q`
Expected: all green; the assembly test runs locally (qwen-agent present). Prior footprint 100 → ~105 tests.

- [ ] **Step 2: Run the Mongo-backed contract pass**

Run: `.venv/bin/pytest -q --store=mongo`
Expected: all green (mongomock when `MONGODB_URI` is unset).

- [ ] **Step 3: Lint the whole tree**

Run: `.venv/bin/ruff check .`
Expected: `All checks passed!`

- [ ] **Step 4: Push and open the PR**

```bash
git push -u origin feat/a9-agent-assembly
gh pr create --title "feat: A.9 — assemble Anamnesis agent + WebUI" \
  --body "Assembles A.1–A.8 into build_agent() + a WebUI entrypoint (app.py). Pure config builders are CI-tested; the assembly test importorskips (spawns the real MCP child under sys.executable). Live WebUI/agent smoke deferred to Qwen gate #1. Design: docs/design/2026-06-24-a9-agent-assembly-design.md."
```

- [ ] **Step 5: Merge after CI is green**

```bash
gh run watch  # or: gh pr checks --watch
gh pr merge --merge --delete-branch
git checkout main && git pull && git branch -d feat/a9-agent-assembly
```

- [ ] **Step 6: Deferred — document, do not fake**

The live "ask the agent / WebUI" smoke (PLAN A.9 Step 3) needs `DASHSCOPE_API_KEY` (Qwen gate #1; `.env` absent). It stays deferred and documented — not stubbed. A.10 wires the seeded demo mint into `CHATBOT_CONFIG["prompt.suggestions"]` and runs the hosted DoD.

---

## Self-Review

**1. Spec coverage** (against `docs/design/2026-06-24-a9-agent-assembly-design.md`):
- D1 pure-builders-+-thin-shell split → Tasks 1 & 2. ✓
- D2 `sys.executable` + absolute fail-fast path → `mcp_entrypoint_path`/`build_function_list` (Task 1) + asserted in `test_build_function_list_...` and the real-spawn assembly test (Task 2). ✓
- D3 `config.require` fail-fast, ordered before the qwen-agent import → `build_agent` (Task 2) + `test_build_agent_missing_dashscope_key_...` (CI-runnable). ✓
- D4 `app.py` demo prompts (`prompt.suggestions` + `verbose` + English `input.placeholder`) → Task 3. ✓
- Testing seam (CI pure + missing-key, `importorskip` assembly, deferred live smoke) → Tasks 1–4. ✓
- Registration subtlety (`from . import tools` before constructing the Assistant) → Task 2 Step 3. ✓

**2. Placeholder scan:** No "TBD/TODO/handle errors/similar to". The only `<...>`-style token is the user-facing "Paste a mint address" copy and the A.10 note — both intentional, not code gaps. ✓

**3. Type consistency:** `build_llm_cfg(api_key: str) -> dict`, `mcp_entrypoint_path() -> Path`, `build_function_list() -> list`, `build_agent() -> Assistant`, `NATIVE_TOOLS` ordering (`recall, remember, assess_risk`), `CHATBOT_CONFIG` keys, and `agent.function_map`/`agent.name` attributes are used identically across tasks and match the verified qwen-agent 0.0.34 API. ✓
