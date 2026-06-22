# Anamnesis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a Solana pre-trade forensic agent whose private, provenance-tracked, bi-temporal memory of deployers compounds across sessions — so a serial rugger's brand-new token is flagged on sight — built on Qwen + Qwen-Agent + an MCP forensic toolset and deployed on Alibaba Cloud.

**Architecture:** A Python core of three pure, independently-testable units — `forensic` (Helius reads → risk signals), `memory` (a bi-temporal knowledge graph over MongoDB with trust-weighted recall), and `risk` (signals + memory → verdict). A thin MCP server exposes the forensic reads; native Qwen-Agent tools expose memory + verdict; a Qwen-Agent `Assistant` orchestrates. Built inward-out (Phase 0 → A → B → C) so a complete, demoable agent exists at every checkpoint.

**Tech Stack:** Python 3.12 · Qwen-Agent (`Assistant`, `@register_tool`, MCP) · `qwen-max` via DashScope-international OpenAI-compat · Helius (DAS + Enhanced Tx) via `httpx` · MongoDB/ApsaraDB via `pymongo` · `mcp` (stdio server) · `pytest` + `ruff` · Alibaba Cloud ECS + ApsaraDB-for-MongoDB.

## Global Constraints

*Every task's requirements implicitly include this section. Values copied verbatim from SPEC.md.*

- **Qwen-only** for all LLM calls. Model `qwen-max` via `model_type:'oai'`, `model_server: https://dashscope-intl.aliyuncs.com/compatible-mode/v1`, key from `DASHSCOPE_API_KEY`. Confirm the exact model id is accepted on the international endpoint on Day 1; keep `qwen-plus`/`qwen-flash` as the high-volume fallback. **Tools cannot be combined with `stream=True`** in OpenAI-compatible mode.
- **Secrets via env only**, never argv/committed: `DASHSCOPE_API_KEY`, `HELIUS_API_KEY`, `MONGODB_URI`. `.env` is gitignored; ship `.env.example` with placeholders.
- **Read-only on-chain** — no signing, trading, or mutating tools. Phase-B "acts" = watchlist + drafted alert with human-in-the-loop only.
- **Alibaba Cloud deploy is a judged hard requirement:** backend on **ECS** (primary; the Node/Python MCP child process is the Velox-style serverless-subprocess risk), memory on **ApsaraDB-for-MongoDB**. Ship a repo code file using the Alibaba Cloud SDK/service (`deploy/apsaradb.py`) + record the backend running on Alibaba Cloud.
- **Public repo**, MIT LICENSE visible, **GPG-signed commits as RECTOR, ZERO AI attribution**.
- **Defensibility:** every artifact (README, video, Devpost text) leads with *memory + measurable compounding + poisoning-defense*, never "scam detection."
- **Python style:** 4-space indent, PEP8, `ruff`-clean, type hints on public functions. Comments only for non-obvious logic.

## File Structure

```
anamnesis/
  pyproject.toml              # deps + ruff + pytest config
  .env.example · .gitignore · LICENSE · README.md · SPEC.md · PLAN.md
  src/anamnesis/
    __init__.py
    config.py                 # env loading (one place; raises actionable errors)
    forensic/
      helius.py               # HeliusClient (httpx) + build_token_profile + deployer_token_history
      signals.py              # PURE: TokenProfile -> list[Signal]   (no I/O)
    memory/
      models.py               # PURE: Provenance, Edge dataclasses + make_edge_id
      repository.py           # Repository protocol + InMemoryRepository (test fake)
      graph.py                # PURE-over-Repository: ForensicMemory (remember/recall/trust_weighted_risk)
      mongo_store.py          # MongoRepository (pymongo / ApsaraDB)
    risk.py                   # PURE: compose_verdict(signals, memory_edges) -> Verdict
    agent/
      prompts.py              # SYSTEM_INSTRUCTION (memory-first, cite-everything, distrust-uncorroborated)
      tools.py                # @register_tool: recall, remember, assess_risk, (B) watchlist_add, draft_alert
      agent.py                # build_agent() -> Assistant (llm_cfg + function_list incl. MCP)
  mcp/
    solana_forensics_mcp.py   # thin MCP stdio server wrapping forensic/
  app.py                      # launches Qwen-Agent WebUI
  scripts/
    check_qwen.py · check_helius.py   # Phase-0 access smokes
    seed_demo.py              # deterministic demo scenario (known-bad deployer + prior rugs + fresh token)
  deploy/
    apsaradb.py               # ApsaraDB connection  (= Alibaba Cloud deploy-proof artifact)
    ecs_setup.md · Dockerfile
  tests/
    conftest.py · test_signals.py · test_memory_models.py · test_memory_graph.py
    test_risk.py · test_helius.py
```

**Testability boundary:** `signals.py`, `memory/*` (except `mongo_store`), and `risk.py` are pure (no network/DB) → full TDD. `helius.py`/`mongo_store.py`/`mcp`/`agent`/`app`/`deploy` are I/O-bound → built with a smoke/integration DoD, not unit-TDD (called out per task).

---

## Phase 0 — Access & tracer bullet (make-or-break; do first)

*Goal: remove every "blocked on access" surprise and prove the whole stack end-to-end before any feature. Some steps are manual account work — that is honest Phase-0 reality, not skippable.*

### Task 0.1: Project scaffold

**Files:** Create `pyproject.toml`, `.gitignore`, `.env.example`, `LICENSE`, `README.md`, `src/anamnesis/__init__.py`, `tests/conftest.py`.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "anamnesis"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "qwen-agent[gui,mcp]>=0.0.30",
  "httpx>=0.27",
  "pymongo>=4.6,<5",
  "mcp>=1.2",
]
[dependency-groups]
dev = ["pytest>=8", "ruff>=0.6", "respx>=0.21"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 2: Write `.gitignore`** (secrets first) — `.env`, `.env.*`, `!.env.example`, `__pycache__/`, `*.py[cod]`, `.venv/`, `.pytest_cache/`, `.ruff_cache/`, `*.log`, `.DS_Store`, `HANDOFF.md`.

- [ ] **Step 3: Write `.env.example`**

```
# Copy to .env (gitignored). Never commit real values.
DASHSCOPE_API_KEY=
HELIUS_API_KEY=
MONGODB_URI=
ANAMNESIS_DB=anamnesis
QWEN_MODEL=qwen-max
```

- [ ] **Step 4: Write `LICENSE` (MIT, "RECTOR <rector@rectorspace.com>"), `README.md` stub** (one-liner + "see SPEC.md"), empty `src/anamnesis/__init__.py`, empty `tests/conftest.py`.

- [ ] **Step 5: Create venv + install + verify ruff/pytest run**

Run: `python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]" && ruff check . && pytest -q`
Expected: install succeeds; `ruff` clean; pytest reports "no tests ran" (exit 5 is OK).

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -S -m "chore: scaffold anamnesis project"
```

### Task 0.2: Access gate — Qwen Cloud (from Indonesia) + model smoke

**Files:** Create `src/anamnesis/config.py`, `scripts/check_qwen.py`.

- [ ] **Step 1:** *(manual)* Register a Qwen Cloud account from Indonesia; generate a key for the **international** endpoint; put it in `.env` as `DASHSCOPE_API_KEY`. **If registration is blocked, STOP and escalate to RECTOR** — this is access gate #1.

- [ ] **Step 2: Write `config.py`** — a single loader with actionable errors:

```python
import os

def require(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(f"{name} is not set. Copy .env.example to .env and fill it.")
    return val

DASHSCOPE_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
QWEN_MODEL = os.environ.get("QWEN_MODEL", "qwen-max")
```

- [ ] **Step 3: Write `scripts/check_qwen.py`** — one-shot OpenAI-compatible call:

```python
from openai import OpenAI
from anamnesis.config import DASHSCOPE_BASE_URL, QWEN_MODEL, require

client = OpenAI(api_key=require("DASHSCOPE_API_KEY"), base_url=DASHSCOPE_BASE_URL)
r = client.chat.completions.create(model=QWEN_MODEL,
        messages=[{"role": "user", "content": "Reply with exactly: OK"}])
print(QWEN_MODEL, "->", r.choices[0].message.content)
```

- [ ] **Step 4: Run + confirm the model id is accepted in-region.** Run: `python scripts/check_qwen.py` → Expected: prints `qwen-max -> OK`. If the id is rejected, try `qwen-plus`, record the accepted id in `.env` `QWEN_MODEL`.

- [ ] **Step 5: Commit** `config.py` + `check_qwen.py` (`add openai` to deps first): `git commit -S -m "feat: qwen access config + model smoke"`.

### Task 0.3: Access gate — Alibaba Cloud credits + ApsaraDB

**Files:** Create `deploy/apsaradb.py`.

- [ ] **Step 1:** *(manual)* Create Alibaba Cloud account; **claim hackathon cloud credits via the voucher form**; provision an **ApsaraDB-for-MongoDB** instance (smallest tier); whitelist your IP; copy the URI into `.env` `MONGODB_URI`. Access gate #2.

- [ ] **Step 2: Write `deploy/apsaradb.py`** — the connection helper that **doubles as the Alibaba-deploy-proof artifact** (this exact file is the link you submit):

```python
"""Alibaba Cloud ApsaraDB for MongoDB connection — the managed memory store.
This module is Anamnesis's proof-of-Alibaba-Cloud-deployment artifact."""
from pymongo import MongoClient
from anamnesis.config import require

def connect() -> MongoClient:
    # MONGODB_URI points at an ApsaraDB-for-MongoDB (Alibaba Cloud) instance.
    return MongoClient(require("MONGODB_URI"), serverSelectionTimeoutMS=10000)
```

- [ ] **Step 3: Smoke — ping ApsaraDB.** Run: `python -c "from deploy.apsaradb import connect; connect().admin.command('ping'); print('ApsaraDB OK')"` → Expected: `ApsaraDB OK`.

- [ ] **Step 4: Commit:** `git commit -S -m "feat: ApsaraDB (Alibaba Cloud) connection + deploy-proof artifact"`.

### Task 0.4: Helius data-layer tracer (the riskiest seam)

**Files:** Create `scripts/check_helius.py`.

- [ ] **Step 1:** Get a Helius API key; set `HELIUS_API_KEY` in `.env`.

- [ ] **Step 2: Write `scripts/check_helius.py`** — pull a real token's authorities via DAS `getAsset`:

```python
import httpx
from anamnesis.config import require

mint = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"  # USDC; replace w/ a test memecoin
url = f"https://mainnet.helius-rpc.com/?api-key={require('HELIUS_API_KEY')}"
r = httpx.post(url, json={"jsonrpc": "2.0", "id": "1", "method": "getAsset",
                          "params": {"id": mint}}, timeout=20).json()
auth = r["result"].get("authorities", [])
print("authorities:", auth)
```

- [ ] **Step 3: Run + confirm** real data returns. Run: `python scripts/check_helius.py` → Expected: prints a non-empty `authorities` list. **This proves the data layer; if it fails, resolve before any feature.**

- [ ] **Step 4: Commit:** `git commit -S -m "chore: helius data-layer tracer"`.

### Task 0.5: End-to-end tracer — minimal agent on ECS

**Files:** Create `app.py` (minimal), `deploy/ecs_setup.md`.

- [ ] **Step 1:** Write a *minimal* `app.py` — a Qwen-Agent `Assistant` with **one** native tool that returns a token's authorities (calls the Task 0.4 logic), launched via the built-in WebUI (`WebUI(agent).run()`).
- [ ] **Step 2:** Provision an **ECS** instance (`deploy/ecs_setup.md`: instance type, security group opening the WebUI port to your IP, `git clone`, `pip install -e .`, env vars). Run `app.py` on ECS.
- [ ] **Step 3: DoD smoke:** open the ECS WebUI URL, ask *"what are the authorities for <mint>?"*, get a real answer. **This is the make-or-break checkpoint: a deployed agent makes one real Solana read on Alibaba Cloud.** If the MCP-child-process model later fails on ECS, the fallback (native function tools) is already proven here.
- [ ] **Step 4: Commit:** `git commit -S -m "feat: end-to-end tracer agent on ECS"`.

---

## Phase A — Lean MemoryAgent (the shippable core)

*Full TDD for the pure units. DoD for the phase: a hosted agent investigates a token, remembers the deployer, and a repeat deployer is an instant memory hit with cited evidence + remembered history.*

### Task A.1: Forensic risk signals (PURE, TDD)

**Files:** Create `src/anamnesis/forensic/__init__.py` (empty), `src/anamnesis/forensic/signals.py`, `tests/test_signals.py`.
**Interfaces — Produces:** `TokenProfile(mint, deployer, mint_authority: str|None, freeze_authority: str|None, lp_secured: bool, top_holder_pct: float, holder_count: int, created_at: str|None)`; `Signal(code: str, severity: str, detail: str)`; `assess_token_signals(p: TokenProfile) -> list[Signal]`. (`None` authority = renounced = safe.)

- [ ] **Step 1: Write the failing test**

```python
from anamnesis.forensic.signals import TokenProfile, assess_token_signals

def _clean() -> TokenProfile:
    return TokenProfile(mint="m", deployer="d", mint_authority=None,
        freeze_authority=None, lp_secured=True, top_holder_pct=3.0, holder_count=500)

def test_clean_token_has_no_signals():
    assert assess_token_signals(_clean()) == []

def test_active_authorities_and_unsecured_lp_flag_high():
    p = TokenProfile(mint="m", deployer="d", mint_authority="d",
        freeze_authority="d", lp_secured=False, top_holder_pct=3.0, holder_count=10)
    codes = {s.code for s in assess_token_signals(p)}
    assert {"MINT_AUTHORITY_ACTIVE", "FREEZE_AUTHORITY_ACTIVE", "LP_NOT_SECURED"} <= codes
    assert all(s.severity == "high" for s in assess_token_signals(p)
               if s.code != "HOLDER_CONCENTRATION")

def test_holder_concentration_threshold():
    p = TokenProfile(mint="m", deployer="d", mint_authority=None, freeze_authority=None,
        lp_secured=True, top_holder_pct=25.0, holder_count=4)
    assert any(s.code == "HOLDER_CONCENTRATION" for s in assess_token_signals(p))
```

- [ ] **Step 2: Run to verify it fails.** Run: `pytest tests/test_signals.py -q` → Expected: FAIL (`ModuleNotFoundError: anamnesis.forensic.signals`).

- [ ] **Step 3: Implement `signals.py`**

```python
from __future__ import annotations
from dataclasses import dataclass

HOLDER_CONCENTRATION_THRESHOLD = 25.0  # percent

@dataclass
class TokenProfile:
    mint: str
    deployer: str
    mint_authority: str | None
    freeze_authority: str | None
    lp_secured: bool
    top_holder_pct: float
    holder_count: int
    created_at: str | None = None

@dataclass
class Signal:
    code: str
    severity: str
    detail: str

def assess_token_signals(p: TokenProfile) -> list[Signal]:
    out: list[Signal] = []
    if p.mint_authority is not None:
        out.append(Signal("MINT_AUTHORITY_ACTIVE", "high",
            f"Mint authority not renounced ({p.mint_authority}); supply can be inflated."))
    if p.freeze_authority is not None:
        out.append(Signal("FREEZE_AUTHORITY_ACTIVE", "high",
            f"Freeze authority active ({p.freeze_authority}); holders can be frozen."))
    if not p.lp_secured:
        out.append(Signal("LP_NOT_SECURED", "high",
            "Liquidity is neither burned nor locked; deployer can pull liquidity."))
    if p.top_holder_pct >= HOLDER_CONCENTRATION_THRESHOLD:
        out.append(Signal("HOLDER_CONCENTRATION", "medium",
            f"Top holder owns {p.top_holder_pct:.1f}% (>= {HOLDER_CONCENTRATION_THRESHOLD:.0f}%)."))
    return out
```

- [ ] **Step 4: Run to verify it passes.** Run: `pytest tests/test_signals.py -q` → Expected: PASS (3 tests).
- [ ] **Step 5: Commit.** `git add -A && git commit -S -m "feat: pure forensic risk-signal extraction"`

### Task A.2: Memory models + repository fake (PURE, TDD)

**Files:** Create `src/anamnesis/memory/__init__.py` (empty), `src/anamnesis/memory/models.py`, `src/anamnesis/memory/repository.py`, `tests/test_memory_models.py`.
**Interfaces — Produces:** `Provenance(source, method, confidence: float)`; `Edge(id, type, src, dst, valid_from, valid_to, recorded_at, superseded_at, provenance)`; `make_edge_id(type, src, dst, recorded_at) -> str`; `Repository` protocol with `upsert_edge(edge)` / `find_edges(entity_key, as_of=None) -> list[Edge]`; `InMemoryRepository`.

- [ ] **Step 1: Write the failing test**

```python
from anamnesis.memory.models import Edge, Provenance, make_edge_id
from anamnesis.memory.repository import InMemoryRepository

def _edge(**kw):
    base = dict(type="DEPLOYED", src="wallet1", dst="mintA",
        valid_from="2026-01-01", valid_to=None, recorded_at="2026-06-01",
        superseded_at=None, provenance=Provenance("helius:getAsset", "first_party", 0.95))
    base.update(kw); base["id"] = make_edge_id(base["type"], base["src"], base["dst"], base["recorded_at"])
    return Edge(**base)

def test_find_by_either_endpoint():
    repo = InMemoryRepository(); repo.upsert_edge(_edge())
    assert len(repo.find_edges("wallet1")) == 1
    assert len(repo.find_edges("mintA")) == 1
    assert repo.find_edges("nobody") == []

def test_current_view_excludes_superseded():
    repo = InMemoryRepository(); e = _edge(); e.superseded_at = "2026-06-05"; repo.upsert_edge(e)
    assert repo.find_edges("wallet1") == []                       # superseded -> hidden now
    assert len(repo.find_edges("wallet1", as_of="2026-06-03")) == 1  # but known as of then
```

- [ ] **Step 2: Run to verify it fails.** Run: `pytest tests/test_memory_models.py -q` → Expected: FAIL (import error).
- [ ] **Step 3: Implement `models.py`**

```python
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Provenance:
    source: str          # e.g. "helius:getAsset"
    method: str          # "first_party" | "derived" | "claimed"
    confidence: float    # 0..1

@dataclass
class Edge:
    id: str
    type: str            # DEPLOYED | FUNDED_BY | PROVIDES_LP | SAME_CLUSTER | RUGGED
    src: str
    dst: str
    valid_from: str
    valid_to: str | None
    recorded_at: str
    superseded_at: str | None
    provenance: Provenance

def make_edge_id(type: str, src: str, dst: str, recorded_at: str) -> str:
    return f"{type}:{src}->{dst}@{recorded_at}"
```

- [ ] **Step 4: Implement `repository.py`**

```python
from __future__ import annotations
from typing import Protocol
from .models import Edge

class Repository(Protocol):
    def upsert_edge(self, edge: Edge) -> None: ...
    def find_edges(self, entity_key: str, as_of: str | None = None) -> list[Edge]: ...

class InMemoryRepository:
    def __init__(self) -> None:
        self._by_id: dict[str, Edge] = {}

    def upsert_edge(self, edge: Edge) -> None:
        self._by_id[edge.id] = edge

    def find_edges(self, entity_key: str, as_of: str | None = None) -> list[Edge]:
        out: list[Edge] = []
        for e in self._by_id.values():
            if entity_key not in (e.src, e.dst):
                continue
            if as_of is None:
                if e.superseded_at is not None:
                    continue
            else:
                if e.recorded_at > as_of:
                    continue
                if e.superseded_at is not None and e.superseded_at <= as_of:
                    continue
            out.append(e)
        return out
```

- [ ] **Step 5: Run + commit.** Run: `pytest tests/test_memory_models.py -q` → PASS. Then `git commit -S -m "feat: bi-temporal memory models + in-memory repository"`.

### Task A.3: ForensicMemory — remember / recall / trust-weighted (PURE, TDD)

**Files:** Create `src/anamnesis/memory/graph.py`, `tests/test_memory_graph.py`.
**Interfaces — Consumes:** `Edge`, `Provenance`, `Repository`. **Produces:** `ForensicMemory(repo)` with `remember(edges, now)`, `recall(entity_key, as_of=None) -> list[Edge]`, `recall_deployer_history(wallet, as_of=None) -> list[Edge]`, `trust_weighted_risk(edges) -> float` (0..1).

- [ ] **Step 1: Write the failing test**

```python
from anamnesis.memory.graph import ForensicMemory
from anamnesis.memory.models import Edge, Provenance, make_edge_id
from anamnesis.memory.repository import InMemoryRepository

def _edge(type, src, dst, rec, conf=0.95, source="helius:getAsset"):
    return Edge(make_edge_id(type, src, dst, rec), type, src, dst,
        rec, None, rec, None, Provenance(source, "first_party", conf))

def test_repeat_deployer_history_is_recalled():
    mem = ForensicMemory(InMemoryRepository())
    mem.remember([_edge("DEPLOYED", "ruggER", "tok1", "2026-02-01"),
                  _edge("RUGGED", "ruggER", "tok1", "2026-02-09")], now="2026-02-09")
    hist = mem.recall_deployer_history("ruggER")
    assert {e.type for e in hist} == {"DEPLOYED", "RUGGED"}

def test_trust_weighted_risk_rewards_corroboration():
    mem = ForensicMemory(InMemoryRepository())
    one = [_edge("RUGGED", "w", "t", "2026-02-01", source="helius:getAsset")]
    many = one + [_edge("RUGGED", "w", "t", "2026-02-01", source="rpc:largestAccounts"),
                  _edge("RUGGED", "w", "t", "2026-02-01", source="enhanced:tx")]
    assert mem.trust_weighted_risk(many) > mem.trust_weighted_risk(one)

def test_uncorroborated_low_confidence_claim_cannot_dominate():
    mem = ForensicMemory(InMemoryRepository())
    poison = [_edge("SAME_CLUSTER", "victim", "badguy", "2026-02-01",
                    conf=0.15, source="claimed:dust")]
    assert mem.trust_weighted_risk(poison) < 0.2   # seeded breadcrumb can't flip a verdict
```

- [ ] **Step 2: Run to verify it fails.** Run: `pytest tests/test_memory_graph.py -q` → Expected: FAIL (import error).
- [ ] **Step 3: Implement `graph.py`**

```python
from __future__ import annotations
from collections import defaultdict
from .models import Edge
from .repository import Repository

class ForensicMemory:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    def remember(self, edges: list[Edge], now: str) -> None:
        for edge in edges:
            for prior in self.repo.find_edges(edge.src):
                if (prior.type, prior.dst) == (edge.type, edge.dst) and prior.superseded_at is None \
                        and prior.id != edge.id:
                    prior.superseded_at = now          # transaction-time supersession
                    self.repo.upsert_edge(prior)
            self.repo.upsert_edge(edge)

    def recall(self, entity_key: str, as_of: str | None = None) -> list[Edge]:
        return self.repo.find_edges(entity_key, as_of)

    def recall_deployer_history(self, wallet: str, as_of: str | None = None) -> list[Edge]:
        return [e for e in self.repo.find_edges(wallet, as_of)
                if e.src == wallet and e.type in ("DEPLOYED", "RUGGED")]

    def trust_weighted_risk(self, edges: list[Edge]) -> float:
        groups: dict[tuple, list[Edge]] = defaultdict(list)
        for e in edges:
            groups[(e.type, e.dst)].append(e)
        score = 0.0
        for items in groups.values():
            if not any(e.type == "RUGGED" for e in items):
                continue
            corroboration = min(len({e.provenance.source for e in items}), 3) / 3.0
            best_conf = max(e.provenance.confidence for e in items)
            score += best_conf * (0.4 + 0.6 * corroboration)
        return min(score, 1.0)
```

- [ ] **Step 4: Run to verify it passes.** Run: `pytest tests/test_memory_graph.py -q` → Expected: PASS (3 tests).
- [ ] **Step 5: Commit.** `git commit -S -m "feat: bi-temporal forensic memory (remember/recall/trust-weighted)"`

### Task A.4: Verdict composition (PURE, TDD)

**Files:** Create `src/anamnesis/risk.py`, `tests/test_risk.py`.
**Interfaces — Consumes:** `Signal` (A.1), `Edge` + `ForensicMemory.trust_weighted_risk` (A.3). **Produces:** `Verdict(level: str, score: float, rationale: str, cited_signals: list, remembered: list)`; `compose_verdict(signals: list[Signal], memory_edges: list[Edge], memory_risk: float) -> Verdict`.

- [ ] **Step 1: Write the failing test**

```python
from anamnesis.risk import compose_verdict
from anamnesis.forensic.signals import Signal

def test_memory_hit_on_repeat_rugger_forces_high():
    # No live signals, but memory says this deployer rugged before -> still HIGH.
    v = compose_verdict(signals=[], memory_edges=["<edge>"], memory_risk=0.8)
    assert v.level == "high"
    assert v.remembered                       # cites the remembered history

def test_clean_token_no_memory_is_low():
    v = compose_verdict(signals=[], memory_edges=[], memory_risk=0.0)
    assert v.level == "low"

def test_live_high_signals_raise_level():
    sigs = [Signal("LP_NOT_SECURED", "high", "x"), Signal("MINT_AUTHORITY_ACTIVE", "high", "y")]
    v = compose_verdict(signals=sigs, memory_edges=[], memory_risk=0.0)
    assert v.level in ("medium", "high") and v.cited_signals
```

- [ ] **Step 2: Run to verify it fails.** Run: `pytest tests/test_risk.py -q` → Expected: FAIL (import error).
- [ ] **Step 3: Implement `risk.py`**

```python
from __future__ import annotations
from dataclasses import dataclass, field
from .forensic.signals import Signal

@dataclass
class Verdict:
    level: str            # "low" | "medium" | "high"
    score: float          # 0..1
    rationale: str
    cited_signals: list[Signal] = field(default_factory=list)
    remembered: list = field(default_factory=list)

def compose_verdict(signals: list[Signal], memory_edges: list, memory_risk: float) -> Verdict:
    live = 0.5 * sum(1 for s in signals if s.severity == "high") \
         + 0.2 * sum(1 for s in signals if s.severity == "medium")
    score = min(max(live, memory_risk), 1.0)          # memory alone can drive risk
    level = "high" if score >= 0.6 else "medium" if score >= 0.3 else "low"
    why = []
    if memory_risk >= 0.6:
        why.append("deployer has remembered prior rug history")
    if any(s.severity == "high" for s in signals):
        why.append("live high-severity on-chain signals present")
    rationale = "; ".join(why) or "no significant risk signals or memory"
    return Verdict(level, score, rationale, cited_signals=signals, remembered=list(memory_edges))
```

- [ ] **Step 4: Run + commit.** Run: `pytest tests/test_risk.py -q` → PASS. Then `git commit -S -m "feat: verdict composition (memory-aware)"`.

### Task A.5: Helius client + profile builder (I/O — smoke + mocked test)

**Files:** Create `src/anamnesis/forensic/helius.py`, add `tests/test_helius.py` (mock HTTP with `respx`).
**Interfaces — Produces:** `HeliusClient(api_key)` with `get_asset(mint) -> dict`, `get_token_largest_accounts(mint) -> list`, `get_assets_by_creator(wallet) -> list`; `build_token_profile(client, mint) -> TokenProfile`; `deployer_token_history(client, wallet) -> list[dict]`.

- [ ] **Step 1:** Write `helius.py` — `httpx` JSON-RPC/REST wrappers; `build_token_profile` maps `getAsset.authorities` → `mint_authority`/`freeze_authority` (None when renounced), `get_token_largest_accounts` → `top_holder_pct`, creator → `deployer`. LP-secured check via the pool/LP-mint burn state.
- [ ] **Step 2:** Write `tests/test_helius.py` mocking `getAsset` JSON for one renounced and one active-authority fixture; assert `build_token_profile` yields the right `TokenProfile` fields. Run: `pytest tests/test_helius.py -q` → PASS.
- [ ] **Step 3: Live smoke** against the Task-0.4 mint: `python -c "from anamnesis.forensic.helius import *; ..."` prints a populated `TokenProfile`. (Confirms field-mapping against real data — the spec's "confirm exact endpoints Day 1.")
- [ ] **Step 4: Commit.** `git commit -S -m "feat: Helius client + token profile builder"`

### Task A.6: Mongo repository (I/O — integration smoke)

**Files:** Create `src/anamnesis/memory/mongo_store.py`.
**Interfaces — Produces:** `MongoRepository(client, db_name)` implementing the `Repository` protocol (A.2) against a `relations` collection; same `upsert_edge`/`find_edges` semantics as `InMemoryRepository`, with a unique index on `id` and indexes on `src`, `dst`.

- [ ] **Step 1:** Implement `MongoRepository` — serialize `Edge`/`Provenance` to documents; `upsert_edge` = `replace_one({"id": edge.id}, doc, upsert=True)`; `find_edges` translates the same bi-temporal filters into a Mongo query. Create indexes in `__init__`.
- [ ] **Step 2: Contract test:** run the **A.2 + A.3 test bodies** against a `MongoRepository` pointed at a local MongoDB (or ApsaraDB) — same assertions must pass (proves the fake and the real store agree). Run: `MONGODB_URI=... pytest tests/test_memory_graph.py -q --store=mongo` (param via `conftest`).
- [ ] **Step 3: Commit.** `git commit -S -m "feat: ApsaraDB/Mongo repository (bi-temporal store)"`

### Task A.7: Agent native tools (wraps pure core)

**Files:** Create `src/anamnesis/agent/tools.py`, `src/anamnesis/agent/prompts.py`, `src/anamnesis/agent/__init__.py`.
**Interfaces — Produces** Qwen-Agent tools (via `@register_tool`): `assess_risk(mint)` (build profile → signals → recall deployer → memory_risk → `compose_verdict` → JSON), `remember(facts)`, `recall(entity_key, as_of=None)`. **Consumes:** A.1, A.3, A.4, A.5, A.6.

- [ ] **Step 1:** Write `prompts.py` `SYSTEM_INSTRUCTION` — memory-first ("always `recall` before judging"), cite evidence + provenance, never fabricate, distrust uncorroborated claims, lead with memory not "scam." (Mirror the spec's instruction.)
- [ ] **Step 2:** Write `tools.py` — each tool a `@register_tool('name')` class whose `call(self, params, **kwargs)` parses JSON args, invokes the pure functions, returns `json5.dumps(...)`. Inject a module-level `ForensicMemory(MongoRepository(...))` + `HeliusClient`.
- [ ] **Step 3: Unit test the pure composition** (`assess_risk`'s non-Qwen path): seed an `InMemoryRepository` with a prior rug for deployer X, call the underlying compose function for a fresh token from X with no live signals → `Verdict.level == "high"` citing memory. (This is the "session-5 catches it" behavior, tested without the LLM.)
- [ ] **Step 4: Commit.** `git commit -S -m "feat: agent tools (assess_risk/remember/recall) over pure core"`

### Task A.8: Forensic MCP server (thin wrapper)

**Files:** Create `mcp/solana_forensics_mcp.py`.
**Interfaces — Produces** an MCP stdio server exposing `get_token_profile`, `get_deployer`, `trace_funding`, `get_holders`, `get_deployer_token_history` — each a thin call into `forensic/helius.py`.

- [ ] **Step 1:** Implement the server with the `mcp` package (stdio); tools return the same dicts `helius.py` produces. `HELIUS_API_KEY` from env.
- [ ] **Step 2: Smoke:** run the server standalone and list/call one tool via an MCP client snippet → returns a real token profile.
- [ ] **Step 3: Commit.** `git commit -S -m "feat: Solana forensics MCP server (wraps Helius)"`

### Task A.9: Assemble the agent + WebUI

**Files:** Rewrite `app.py`; create `src/anamnesis/agent/agent.py`.
**Interfaces — Produces:** `build_agent() -> Assistant` (llm_cfg per Global Constraints; `function_list` = the MCP `{'mcpServers': {...}}` block + `['assess_risk','remember','recall']`).

- [ ] **Step 1:** Implement `agent.py` `build_agent()` exactly per SPEC §"Qwen-Agent wiring" (model `qwen-max`, `model_type:'oai'`, intl base URL, system message from `prompts.py`).
- [ ] **Step 2:** `app.py` = `from qwen_agent.gui import WebUI; WebUI(build_agent()).run()`.
- [ ] **Step 3: Manual smoke (local):** ask "should I ape <mint>?" → agent recalls (empty first), investigates via MCP, returns a cited verdict.
- [ ] **Step 4: Commit.** `git commit -S -m "feat: assemble Anamnesis agent + WebUI"`

### Task A.10: Deterministic demo seed + deploy + Phase-A DoD

**Files:** Create `scripts/seed_demo.py`.

- [ ] **Step 1:** Write `seed_demo.py` — insert a **known-bad deployer** with two prior `DEPLOYED`+`RUGGED` tokens into the memory store, plus register a **fresh token** from that same deployer (clean-looking live signals) so the "session-5 instant catch" is reproducible. Deterministic ids/dates (no randomness).
- [ ] **Step 2:** Deploy the full agent to **ECS** (per `ecs_setup.md`), memory on **ApsaraDB**. Record the backend running on Alibaba Cloud (deploy-proof clip).
- [ ] **Step 3: Phase-A DoD (hosted):** on the ECS URL — investigate the fresh token → agent **instantly flags HIGH from memory**, citing the deployer's two prior rugs + the live signals. Capture the cold-vs-memory latency delta (the N× metric). **Scope-stable checkpoint.**
- [ ] **Step 4: Commit.** `git commit -S -m "feat: demo seed + Phase-A hosted on Alibaba Cloud"`

---

## Phase B — MemoryAgent that acts (task outline; scope-freeze after)

*Layered on the shippable A. Right-sized tasks; full TDD code written at execution time per task.*

- [ ] **B.1 — Watchlist + alert tools (TDD):** `watchlist_add(mint, reason)` and `draft_alert(mint) -> {channel, body, evidence}` in `agent/tools.py`; pure draft-builder unit-tested (asserts the evidence chain + remembered history appear in the body). Commit.
- [ ] **B.2 — Threshold trigger:** in `assess_risk`, when `Verdict.level == "high"` **and** memory corroborates a repeat offender, auto-call `watchlist_add` + `draft_alert`; **human-in-the-loop** gate before any webhook send (no auto-send). Unit-test the trigger predicate. Commit.
- [ ] **B.3 — Relationship-graph view:** a minimal endpoint/page rendering the deployer↔funder↔token↔cluster edges for a mint (read from the memory store) for the "watch it connect the dots" demo. Smoke. Commit.
- [ ] **B.4 — Human-in-loop confirm + optional Telegram/Discord webhook send** (env-gated URL; off by default). Smoke. Commit. **→ SCOPE FREEZE.**

## Phase C — Bi-temporal time-travel (stretch on shippable B)

*Only after B is hosted + demoed. Each task ends shippable; abandon cleanly if the clock runs out — B already satisfies the submission.*

- [ ] **C.1 — Valid-time axis (TDD):** extend `remember` to set `valid_to` when a fact stops being true on-chain (e.g., authority later renounced); test that `recall(..., valid_at=T)` distinguishes on-chain truth-at-T from belief-at-T. Commit.
- [ ] **C.2 — Time-travel query + tool:** `recall(entity, as_of=...)` surfaced as an agent capability ("what did we know about this deployer last week"); test dual-axis separation end-to-end. Commit.
- [ ] **C.3 — Deepen poisoning defense:** add a `claimed`-method decay + corroboration-source independence check to `trust_weighted_risk`; test that a burst of same-source seeded edges does not raise risk. Commit.

## Submission (final days — not engineering)

- [ ] **S.1 — README + SVG architecture diagram** (`assets/`, dark-bg), Qwen/MCP/memory/poisoning notes, "synthetic-demo / not financial advice," lead-with-memory framing. Commit.
- [ ] **S.2 — Secret scan** (`git grep` for URIs/keys; confirm `.env` gitignored, only `.env.example` shipped). Commit.
- [ ] **S.3 — <3-min demo video** (YouTube): cold investigation → verdict → two more from the same deployer → 4th fresh token **instant memory flag** + graph cluster → N× metric → one line on Qwen + Qwen-Agent + MCP + Alibaba.
- [ ] **S.4 — Alibaba deploy proof:** link `deploy/apsaradb.py` (+ ECS) in the Devpost form; attach the backend-on-Alibaba recording.
- [ ] **S.5 — Devpost form:** track = **MemoryAgent**; repo + hosted URL + video; optional blog post. Submit **≥3h before** Jul 9 2:00 PM PDT.

---

## Self-Review (run against SPEC.md)

**Spec coverage:** MemoryAgent track ✓(A.7 prompts, framing) · forensic signals ✓(A.1) · deployer prior-token history = compounding crux ✓(A.3/A.5/A.7) · bi-temporal graph ✓(A.2/A.3 + C.1/C.2) · provenance-weighted poisoning defense ✓(A.3 + C.3) · Qwen-Agent + qwen-max + DashScope-intl ✓(A.9, Global Constraints) · MCP forensic toolset ✓(A.8) · ApsaraDB + ECS + deploy proof ✓(0.3/0.5/A.10/S.4) · "acts" path ✓(B) · WebUI + graph view ✓(A.9/B.3) · demo N× metric ✓(A.10/S.3) · deliverables ✓(S.*). No uncovered spec requirement.

**Placeholder scan:** Phase 0 + A carry complete, runnable test+impl code. B/C/S are **intentionally** right-sized outlines (per the inward-out spec quarantining C as stretch) with concrete files, interfaces, and DoD — not vague "implement later." Flag at execution: write each B/C task's failing test first.

**Type consistency:** `TokenProfile`/`Signal` (A.1) consumed unchanged in A.5/A.7/A.4; `Edge`/`Provenance`/`make_edge_id` (A.2) used identically in A.3/A.6/A.7; `Repository.find_edges(entity_key, as_of)` signature identical across InMemory (A.2) and Mongo (A.6); `compose_verdict(signals, memory_edges, memory_risk)` (A.4) called with those exact args in A.7. Consistent.
