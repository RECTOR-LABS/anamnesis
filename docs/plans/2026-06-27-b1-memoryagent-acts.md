# B.1 — MemoryAgent that acts (watchlist_add + draft_alert) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When `assess_risk` yields a verdict with score ≥ HIGH (0.6), automatically watchlist the deployer and draft a human-reviewable (never-sent) alert.

**Architecture:** A thin "acts" layer over the existing pure core. `assess.py`/`risk.py`/`memory/graph.py` are unchanged in behaviour. Watchlist entries are a new `WATCHLISTED` bi-temporal memory edge (deliberately unscored, so no risk feedback loop); alert drafts live in a new `AlertStore` (InMemory + Mongo, mirroring `Repository`). An orchestrator (`assess_and_act`) performs the writes; the agent's `assess_risk` tool is upgraded to call it.

**Tech Stack:** Python ≥3.12, pymongo (+ mongomock in tests), pytest, ruff. qwen-agent only for the thin `@register_tool` wrappers (CI-skipped via `importorskip`).

## Global Constraints

- Python ≥3.12; `from __future__ import annotations` at the top of every new module (matches the codebase; these are NOT FastMCP tool modules, so it is safe here).
- ruff must stay clean (`line-length = 100`, default rule set). Keep every line ≤ 100 columns. 4-space indentation.
- Pure logic (`memory/alerts.py`, `agent/actions.py`, `agent/serialize.py`) MUST import without qwen-agent / mcp / openai — they run in CI. The `@register_tool` wrappers live inside the existing `if register_tool is not None:` block in `agent/tools.py` and are CI-skipped.
- New edge type string is exactly `"WATCHLISTED"`; its provenance `method` is exactly `"derived"` (a valid method in `METHOD_TRUST`), `source` is `"assess_risk"`.
- `WATCHLISTED` must NOT be added to `RISK_WEIGHTS` / `TYPE_CEILING` in `memory/graph.py` — it is recall-able but never scored (no feedback loop).
- Tests must pass under both `pytest` (in-memory default) and `pytest --store=mongo` (mongomock).
- Commits: GPG-signed (`git commit -S`), conventional type, **zero AI attribution** (no `Co-Authored-By`, no tool mentions).
- All `now`/timestamps are passed in by callers (the agent stamps its own clock); pure functions never call `datetime.now()`.

---

### Task 1: `AlertDraft` + `InMemoryAlertStore`

**Files:**
- Create: `src/anamnesis/memory/alerts.py`
- Test: `tests/test_alerts_store.py`

**Interfaces:**
- Produces:
  - `AlertDraft` (frozen dataclass): `id:str, deployer:str, mint:str, severity:str, score:float, rationale:str, evidence:list[str], message:str, status:str, created_at:str`
  - `AlertStore` (Protocol): `add_draft(draft:AlertDraft)->AlertDraft`, `list_pending()->list[AlertDraft]`, `get(draft_id:str)->AlertDraft|None`
  - `InMemoryAlertStore` implementing `AlertStore`; `add_draft` is idempotent per `(deployer, mint)` among `status=="pending"` (returns the existing pending draft).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_alerts_store.py
from anamnesis.memory.alerts import AlertDraft, InMemoryAlertStore


def _draft(deployer="dep", mint="mintZ", created="2026-06-27", did=None):
    return AlertDraft(
        id=did or f"alert:{deployer}->{mint}@{created}",
        deployer=deployer, mint=mint, severity="high", score=0.72,
        rationale="deployer has remembered prior rug history",
        evidence=["memory: RUGGED dep->t1 (method=first_party)"],
        message="[HIGH] rug-risk on mint mintZ", status="pending", created_at=created,
    )


def test_add_list_get():
    store = InMemoryAlertStore()
    d = store.add_draft(_draft())
    assert store.list_pending() == [d]
    assert store.get(d.id) == d


def test_add_draft_idempotent_per_deployer_mint_pending():
    store = InMemoryAlertStore()
    first = store.add_draft(_draft(created="2026-06-27"))
    again = store.add_draft(_draft(created="2026-06-28", did="alert:dep->mintZ@2026-06-28"))
    assert again == first                      # same (deployer,mint) pending -> existing returned
    assert len(store.list_pending()) == 1
```

- [ ] **Step 2: Run it, verify it fails**

Run: `pytest tests/test_alerts_store.py -q`
Expected: FAIL — `ModuleNotFoundError: anamnesis.memory.alerts`.

- [ ] **Step 3: Implement `memory/alerts.py`**

```python
"""Alert drafts — the human-in-the-loop review queue for B.1.

A high-risk verdict auto-drafts an AlertDraft (status="pending"); it is NEVER
auto-sent. AlertStore mirrors the Repository pattern so the same contract is
proven against the in-memory fake and the Mongo store.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AlertDraft:
    id: str
    deployer: str
    mint: str
    severity: str          # = verdict.level ("low" | "medium" | "high")
    score: float
    rationale: str
    evidence: list[str]    # human-readable lines from cited signals + remembered edges
    message: str           # fully rendered, human-readable alert text
    status: str            # "pending" (never auto-"sent")
    created_at: str


class AlertStore(Protocol):
    def add_draft(self, draft: AlertDraft) -> AlertDraft: ...

    def list_pending(self) -> list[AlertDraft]: ...

    def get(self, draft_id: str) -> AlertDraft | None: ...


class InMemoryAlertStore:
    """Test fake. `add_draft` is idempotent per (deployer, mint) among pending drafts:
    re-drafting an already-pending pair returns the existing draft (no alert spam)."""

    def __init__(self) -> None:
        self._by_id: dict[str, AlertDraft] = {}

    def add_draft(self, draft: AlertDraft) -> AlertDraft:
        for d in self._by_id.values():
            if d.status == "pending" and d.deployer == draft.deployer and d.mint == draft.mint:
                return d
        self._by_id[draft.id] = draft
        return draft

    def list_pending(self) -> list[AlertDraft]:
        pending = [d for d in self._by_id.values() if d.status == "pending"]
        return sorted(pending, key=lambda d: (d.created_at, d.id))

    def get(self, draft_id: str) -> AlertDraft | None:
        return self._by_id.get(draft_id)
```

- [ ] **Step 4: Run it, verify it passes**

Run: `pytest tests/test_alerts_store.py -q` → Expected: PASS (2 passed).
Run: `ruff check src/anamnesis/memory/alerts.py tests/test_alerts_store.py` → Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add src/anamnesis/memory/alerts.py tests/test_alerts_store.py
git commit -S -m "feat: AlertDraft + InMemoryAlertStore (B.1 alert queue)"
```

---

### Task 2: `MongoAlertStore` + cross-backend contract

**Files:**
- Modify: `src/anamnesis/memory/alerts.py` (append `MongoAlertStore` + doc helpers)
- Modify: `tests/conftest.py` (add `alerts` fixture, mirroring `repo`)
- Modify: `tests/test_alerts_store.py` (append contract tests using the `alerts` fixture)

**Interfaces:**
- Consumes: `AlertDraft`, `AlertStore` (Task 1); `CONTRACT_DB` (conftest).
- Produces: `MongoAlertStore(client, db_name)` (collection `"alert_drafts"`); pytest fixture `alerts` yielding the selected backend.

- [ ] **Step 1: Write the failing contract tests + fixture**

Append to `tests/test_alerts_store.py`:

```python
def test_contract_add_list_get(alerts):
    d = alerts.add_draft(_draft())
    assert [x.id for x in alerts.list_pending()] == [d.id]
    assert alerts.get(d.id).mint == "mintZ"


def test_contract_idempotent_pending(alerts):
    alerts.add_draft(_draft(created="2026-06-27"))
    alerts.add_draft(_draft(created="2026-06-28", did="alert:dep->mintZ@2026-06-28"))
    assert len(alerts.list_pending()) == 1
```

Append the `alerts` fixture to `tests/conftest.py`:

```python
@pytest.fixture
def alerts(request: pytest.FixtureRequest):
    """A fresh, isolated AlertStore for the selected --store backend (mirrors `repo`)."""
    from anamnesis.memory.alerts import InMemoryAlertStore

    if request.config.getoption("--store") == "memory":
        yield InMemoryAlertStore()
        return

    from anamnesis.memory.alerts import MongoAlertStore

    if CONTRACT_DB == config.ANAMNESIS_DB:
        raise RuntimeError(
            f"contract DB {CONTRACT_DB!r} must differ from the production db "
            "(config.ANAMNESIS_DB); refusing to run to avoid dropping real memory"
        )
    if uri := os.environ.get("ANAMNESIS_MONGODB_URI"):
        from pymongo import MongoClient

        client = MongoClient(uri, serverSelectionTimeoutMS=10000)
    else:
        mongomock = pytest.importorskip("mongomock")
        client = mongomock.MongoClient()
    try:
        client.drop_database(CONTRACT_DB)
        yield MongoAlertStore(client, CONTRACT_DB)
    finally:
        try:
            client.drop_database(CONTRACT_DB)
        finally:
            client.close()
```

- [ ] **Step 2: Run, verify failure**

Run: `pytest tests/test_alerts_store.py -q --store=mongo`
Expected: FAIL — `ImportError: cannot import name 'MongoAlertStore'`.

- [ ] **Step 3: Implement `MongoAlertStore`**

Append to `src/anamnesis/memory/alerts.py`:

```python
from typing import Any  # add to the existing imports at top of file

ALERTS_COLLECTION = "alert_drafts"


def _draft_to_doc(d: AlertDraft) -> dict[str, Any]:
    return {
        "id": d.id, "deployer": d.deployer, "mint": d.mint, "severity": d.severity,
        "score": d.score, "rationale": d.rationale, "evidence": list(d.evidence),
        "message": d.message, "status": d.status, "created_at": d.created_at,
    }


def _draft_from_doc(doc: dict[str, Any]) -> AlertDraft:
    return AlertDraft(
        id=doc["id"], deployer=doc["deployer"], mint=doc["mint"], severity=doc["severity"],
        score=doc["score"], rationale=doc["rationale"], evidence=list(doc["evidence"]),
        message=doc["message"], status=doc["status"], created_at=doc["created_at"],
    )


class MongoAlertStore:
    """`AlertStore` over a MongoDB / ApsaraDB `alert_drafts` collection. Same idempotency
    contract as InMemoryAlertStore: one pending draft per (deployer, mint)."""

    def __init__(self, client: Any, db_name: str) -> None:
        self._col = client[db_name][ALERTS_COLLECTION]
        self._col.create_index("id", unique=True)
        self._col.create_index([("deployer", 1), ("mint", 1), ("status", 1)])

    def add_draft(self, draft: AlertDraft) -> AlertDraft:
        existing = self._col.find_one(
            {"deployer": draft.deployer, "mint": draft.mint, "status": "pending"}
        )
        if existing is not None:
            return _draft_from_doc(existing)
        self._col.replace_one({"id": draft.id}, _draft_to_doc(draft), upsert=True)
        return draft

    def list_pending(self) -> list[AlertDraft]:
        docs = self._col.find({"status": "pending"}).sort([("created_at", 1), ("id", 1)])
        return [_draft_from_doc(d) for d in docs]

    def get(self, draft_id: str) -> AlertDraft | None:
        doc = self._col.find_one({"id": draft_id})
        return _draft_from_doc(doc) if doc is not None else None
```

- [ ] **Step 4: Run both backends, verify pass**

Run: `pytest tests/test_alerts_store.py -q` → PASS
Run: `pytest tests/test_alerts_store.py -q --store=mongo` → PASS
Run: `ruff check src/anamnesis/memory/alerts.py tests/conftest.py` → clean

- [ ] **Step 5: Commit**

```bash
git add src/anamnesis/memory/alerts.py tests/conftest.py tests/test_alerts_store.py
git commit -S -m "feat: MongoAlertStore + cross-backend alert-store contract"
```

---

### Task 3: `agent/serialize.py` (shared dict serializers) + tools.py refactor

**Files:**
- Create: `src/anamnesis/agent/serialize.py`
- Modify: `src/anamnesis/agent/tools.py` (remove local `_edge_to_dict`/`_verdict_to_dict`; import from serialize)
- Test: `tests/test_serialize.py` (new) + existing `tests/test_agent_tools.py` must still pass

**Interfaces:**
- Consumes: `Edge` (`memory/models`), `Verdict` (`risk`), `AlertDraft` (`memory/alerts`).
- Produces: `edge_to_dict(e:Edge)->dict`, `verdict_to_dict(v:Verdict)->dict`, `draft_to_dict(d:AlertDraft)->dict`. (DRY: actions.py and tools.py both import these — avoids a tools↔actions import cycle.)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_serialize.py
from anamnesis.agent.serialize import draft_to_dict, verdict_to_dict
from anamnesis.memory.alerts import AlertDraft
from anamnesis.risk import Verdict


def test_verdict_to_dict_rounds_and_lists():
    v = Verdict(level="high", score=0.7234, rationale="r")
    out = verdict_to_dict(v)
    assert out["level"] == "high" and out["score"] == 0.7234
    assert out["signals"] == [] and out["remembered"] == []


def test_draft_to_dict_roundtrips_fields():
    d = AlertDraft(id="a1", deployer="dep", mint="m", severity="high", score=0.72,
                   rationale="r", evidence=["e1"], message="msg", status="pending",
                   created_at="2026-06-27")
    out = draft_to_dict(d)
    assert out["id"] == "a1" and out["mint"] == "m" and out["status"] == "pending"
    assert out["evidence"] == ["e1"]
```

- [ ] **Step 2: Run, verify failure**

Run: `pytest tests/test_serialize.py -q`
Expected: FAIL — `ModuleNotFoundError: anamnesis.agent.serialize`.

- [ ] **Step 3: Create `agent/serialize.py` and refactor `tools.py`**

Create `src/anamnesis/agent/serialize.py` (move the two functions verbatim from tools.py, add `draft_to_dict`):

```python
"""JSON-able serializers for edges, verdicts, and alert drafts.

Shared by agent/tools.py and agent/actions.py so neither imports the other
(no cycle) and the dict shapes stay identical across the tool surface.
"""
from __future__ import annotations

from ..memory.alerts import AlertDraft
from ..memory.models import Edge
from ..risk import Verdict


def edge_to_dict(e: Edge) -> dict:
    return {
        "type": e.type, "src": e.src, "dst": e.dst,
        "method": e.provenance.method, "source": e.provenance.source,
        "confidence": e.provenance.confidence, "recorded_at": e.recorded_at,
        "valid_from": e.valid_from, "valid_to": e.valid_to, "superseded_at": e.superseded_at,
    }


def verdict_to_dict(v: Verdict) -> dict:
    return {
        "level": v.level, "score": round(v.score, 4), "rationale": v.rationale,
        "signals": [
            {"code": s.code, "severity": s.severity, "detail": s.detail} for s in v.cited_signals
        ],
        "remembered": [edge_to_dict(e) for e in v.remembered],
    }


def draft_to_dict(d: AlertDraft) -> dict:
    return {
        "id": d.id, "deployer": d.deployer, "mint": d.mint, "severity": d.severity,
        "score": d.score, "rationale": d.rationale, "evidence": list(d.evidence),
        "message": d.message, "status": d.status, "created_at": d.created_at,
    }
```

In `src/anamnesis/agent/tools.py`: delete the local `_edge_to_dict` (lines ~35-47) and `_verdict_to_dict` (lines ~50-59) definitions, and add this import near the other `from ..` imports:

```python
from .serialize import edge_to_dict, verdict_to_dict
```

Then update the two call sites in tools.py:
- in `recall_handler`: `"edges": [edge_to_dict(e) for e in edges]`
- in `assess_risk_handler`: `return verdict_to_dict(verdict)`

- [ ] **Step 4: Run, verify pass + no regression**

Run: `pytest tests/test_serialize.py tests/test_agent_tools.py -q` → PASS (all)
Run: `ruff check src/anamnesis/agent/serialize.py src/anamnesis/agent/tools.py` → clean

- [ ] **Step 5: Commit**

```bash
git add src/anamnesis/agent/serialize.py src/anamnesis/agent/tools.py tests/test_serialize.py
git commit -S -m "refactor: extract shared edge/verdict/draft serializers to agent/serialize.py"
```

---

### Task 4: `watchlist_add`

**Files:**
- Create: `src/anamnesis/agent/actions.py`
- Test: `tests/test_actions.py`

**Interfaces:**
- Consumes: `ForensicMemory`, `make_edge`, `Provenance`.
- Produces: `watchlist_add(memory:ForensicMemory, deployer:str, mint:str, score:float, now:str) -> Edge` — writes a `WATCHLISTED` edge (method `"derived"`, confidence clamped to [0,1]); returns the edge.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_actions.py
from anamnesis.agent.actions import watchlist_add
from anamnesis.memory.graph import ForensicMemory
from anamnesis.memory.repository import InMemoryRepository


def test_watchlist_add_writes_derived_edge_and_recalls():
    mem = ForensicMemory(InMemoryRepository())
    edge = watchlist_add(mem, "dep", "mintZ", 0.72, "2026-06-27")
    assert edge.type == "WATCHLISTED" and edge.src == "dep" and edge.dst == "mintZ"
    assert edge.provenance.method == "derived" and edge.provenance.source == "assess_risk"
    assert abs(edge.provenance.confidence - 0.72) < 1e-9
    assert any(e.type == "WATCHLISTED" and e.dst == "mintZ" for e in mem.recall("dep"))


def test_watchlist_does_not_inflate_risk_no_feedback_loop():
    mem = ForensicMemory(InMemoryRepository())
    watchlist_add(mem, "dep", "mintZ", 1.0, "2026-06-27")
    # WATCHLISTED is not a scored type -> memory risk stays 0 (it records, it does not accuse)
    assert mem.trust_weighted_risk(mem.recall("dep")) == 0.0


def test_watchlist_re_add_supersedes_not_duplicates():
    mem = ForensicMemory(InMemoryRepository())
    watchlist_add(mem, "dep", "mintZ", 0.7, "2026-06-27")
    watchlist_add(mem, "dep", "mintZ", 0.9, "2026-06-28")
    current = [e for e in mem.recall("dep") if e.type == "WATCHLISTED" and e.dst == "mintZ"]
    assert len(current) == 1  # higher-trust re-add supersedes the prior; no duplicate
```

- [ ] **Step 2: Run, verify failure**

Run: `pytest tests/test_actions.py -q`
Expected: FAIL — `ModuleNotFoundError: anamnesis.agent.actions`.

- [ ] **Step 3: Implement `agent/actions.py`**

```python
"""The 'acts' layer — watchlist + alert drafting triggered off a verdict.

Pure over injected memory + alert stores (CI-testable without qwen-agent). The
pure verdict pipeline (assess.py) is unchanged; this module performs the writes.
"""
from __future__ import annotations

from ..memory.graph import ForensicMemory
from ..memory.models import Edge, Provenance, make_edge


def watchlist_add(
    memory: ForensicMemory, deployer: str, mint: str, score: float, now: str
) -> Edge:
    """Record the deployer on the watchlist (a WATCHLISTED edge, deployer -> triggering mint).

    Provenance is `derived` (this is inferred from the verdict, not a first-party on-chain
    observation) — and WATCHLISTED is not a scored type, so a watchlist entry is recall-able
    but can never inflate a future verdict (no feedback loop).
    """
    edge = make_edge(
        "WATCHLISTED", deployer, mint,
        valid_from=now, recorded_at=now,
        provenance=Provenance(
            source="assess_risk", method="derived", confidence=min(1.0, max(0.0, score))
        ),
    )
    memory.remember([edge], now=now)
    return edge
```

- [ ] **Step 4: Run, verify pass**

Run: `pytest tests/test_actions.py -q` → PASS (3 passed)
Run: `ruff check src/anamnesis/agent/actions.py tests/test_actions.py` → clean

- [ ] **Step 5: Commit**

```bash
git add src/anamnesis/agent/actions.py tests/test_actions.py
git commit -S -m "feat: watchlist_add — WATCHLISTED memory edge (unscored, no feedback loop)"
```

---

### Task 5: `draft_alert`

**Files:**
- Modify: `src/anamnesis/agent/actions.py` (append)
- Test: `tests/test_actions.py` (append)

**Interfaces:**
- Consumes: `AlertStore`, `AlertDraft` (`memory/alerts`); `Verdict` (`risk`).
- Produces: `draft_alert(alerts:AlertStore, verdict:Verdict, deployer:str, mint:str, now:str) -> AlertDraft` — renders + persists a `pending` draft (idempotent per `(deployer, mint)` via the store).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_actions.py`:

```python
from anamnesis.agent.actions import draft_alert
from anamnesis.forensic.signals import Signal
from anamnesis.memory.alerts import InMemoryAlertStore
from anamnesis.risk import Verdict


def _verdict():
    return Verdict(
        level="high", score=0.72, rationale="deployer has remembered prior rug history",
        cited_signals=[Signal("MINT_AUTHORITY_ACTIVE", "high", "supply can be inflated")],
        remembered=[],
    )


def test_draft_alert_builds_and_persists_pending():
    store = InMemoryAlertStore()
    d = draft_alert(store, _verdict(), "dep", "mintZ", "2026-06-27")
    assert d.severity == "high" and d.mint == "mintZ" and d.status == "pending"
    assert any("MINT_AUTHORITY_ACTIVE" in line for line in d.evidence)
    assert "mintZ" in d.message and "0.72" in d.message
    assert store.list_pending() == [d]


def test_draft_alert_idempotent_per_deployer_mint():
    store = InMemoryAlertStore()
    draft_alert(store, _verdict(), "dep", "mintZ", "2026-06-27")
    draft_alert(store, _verdict(), "dep", "mintZ", "2026-06-28")
    assert len(store.list_pending()) == 1
```

- [ ] **Step 2: Run, verify failure**

Run: `pytest tests/test_actions.py -q`
Expected: FAIL — `ImportError: cannot import name 'draft_alert'`.

- [ ] **Step 3: Implement (append to `agent/actions.py`)**

Add the import at top: `from ..memory.alerts import AlertDraft, AlertStore` and `from ..risk import Verdict`. Then:

```python
def _evidence_lines(verdict: Verdict) -> list[str]:
    lines = [f"signal: {s.code} ({s.severity}) — {s.detail}" for s in verdict.cited_signals]
    lines += [
        f"memory: {e.type} {e.src}->{e.dst} (method={e.provenance.method})"
        for e in verdict.remembered
    ]
    return lines


def _render_message(deployer: str, mint: str, verdict: Verdict) -> str:
    head = (
        f"[{verdict.level.upper()}] rug-risk on mint {mint} "
        f"(deployer {deployer}, score {verdict.score:.2f})"
    )
    ev = _evidence_lines(verdict)
    if ev:
        return head + "\n" + verdict.rationale + "\nEvidence:\n" + "\n".join(
            f"  - {x}" for x in ev
        )
    return head + "\n" + verdict.rationale


def draft_alert(
    alerts: AlertStore, verdict: Verdict, deployer: str, mint: str, now: str
) -> AlertDraft:
    """Render a pending alert draft from a verdict and persist it (idempotent per
    (deployer, mint) — the store returns the existing pending draft for a repeat pair).
    Drafts are never auto-sent: a human reviews `list_pending_alerts` and decides."""
    draft = AlertDraft(
        id=f"alert:{deployer}->{mint}@{now}",
        deployer=deployer, mint=mint, severity=verdict.level, score=round(verdict.score, 4),
        rationale=verdict.rationale, evidence=_evidence_lines(verdict),
        message=_render_message(deployer, mint, verdict), status="pending", created_at=now,
    )
    return alerts.add_draft(draft)
```

- [ ] **Step 4: Run, verify pass**

Run: `pytest tests/test_actions.py -q` → PASS
Run: `ruff check src/anamnesis/agent/actions.py tests/test_actions.py` → clean

- [ ] **Step 5: Commit**

```bash
git add src/anamnesis/agent/actions.py tests/test_actions.py
git commit -S -m "feat: draft_alert — render + persist pending alert draft (idempotent)"
```

---

### Task 6: `assess_and_act` (the auto-trigger orchestrator) — the DoD

**Files:**
- Modify: `src/anamnesis/agent/actions.py` (append)
- Test: `tests/test_actions.py` (append)

**Interfaces:**
- Consumes: `assess_risk` (`assess`), `TokenProfile` (`forensic/signals`), `HIGH_THRESHOLD` (`risk`), `verdict_to_dict`/`draft_to_dict` (`agent/serialize`), and Task 4/5 functions.
- Produces: `assess_and_act(memory, alerts, build_profile, mint, now, *, as_of=None) -> dict` — verdict dict plus `acted:bool`, `watchlisted:dict|None`, `alert:dict|None`, and `error:str` on a write failure.

- [ ] **Step 1: Write the failing tests (incl. the DoD)**

Append to `tests/test_actions.py`:

```python
from anamnesis.agent.actions import assess_and_act
from anamnesis.forensic.signals import LpAssessment, LpStatus, TokenProfile
from anamnesis.memory.models import Provenance as _Prov
from anamnesis.memory.models import make_edge


def _rugger_memory():
    mem = ForensicMemory(InMemoryRepository())
    mem.remember(
        [make_edge("RUGGED", "ruggerX", "tokA", valid_from="2026-01-01",
                   recorded_at="2026-01-01", provenance=_Prov("helius:getAsset", "first_party", 0.95)),
         make_edge("RUGGED", "ruggerX", "tokB", valid_from="2026-01-05",
                   recorded_at="2026-01-05", provenance=_Prov("helius:getAsset", "first_party", 0.95))],
        now="2026-01-05",
    )
    return mem


def _clean_profile(deployer, mint="tokFresh"):
    return TokenProfile(mint=mint, deployer=deployer, mint_authority=None, freeze_authority=None,
                        lp=LpAssessment(LpStatus.SECURED), top_holder_pct=2.0, holder_count=300)


def test_assess_and_act_high_verdict_watchlists_and_drafts():
    # DoD: a remembered serial rugger's fresh, clean-looking token -> HIGH -> watchlist + alert.
    mem, store = _rugger_memory(), InMemoryAlertStore()
    out = assess_and_act(mem, store, lambda m: _clean_profile("ruggerX"), "tokFresh", "2026-06-27")
    assert out["level"] == "high" and out["acted"] is True
    assert out["watchlisted"]["deployer"] == "ruggerX"
    assert out["alert"]["mint"] == "tokFresh" and out["alert"]["status"] == "pending"
    assert [e for e in mem.recall("ruggerX") if e.type == "WATCHLISTED"]
    assert len(store.list_pending()) == 1


def test_assess_and_act_low_verdict_does_not_act():
    mem, store = ForensicMemory(InMemoryRepository()), InMemoryAlertStore()
    out = assess_and_act(mem, store, lambda m: _clean_profile("freshWallet", "m"), "m", "2026-06-27")
    assert out["level"] == "low" and out["acted"] is False
    assert out["watchlisted"] is None and out["alert"] is None
    assert store.list_pending() == []


def test_assess_and_act_preserves_verdict_when_write_fails():
    class _BoomStore:
        def add_draft(self, d):
            raise RuntimeError("mongo down")

        def list_pending(self):
            return []

        def get(self, i):
            return None

    out = assess_and_act(_rugger_memory(), _BoomStore(),
                         lambda m: _clean_profile("ruggerX"), "tokFresh", "2026-06-27")
    assert out["level"] == "high"          # verdict preserved despite the failed write
    assert out["acted"] is False and "error" in out
```

- [ ] **Step 2: Run, verify failure**

Run: `pytest tests/test_actions.py -q`
Expected: FAIL — `ImportError: cannot import name 'assess_and_act'`.

- [ ] **Step 3: Implement (append to `agent/actions.py`)**

Add imports at top:

```python
from collections.abc import Callable

from ..assess import assess_risk
from ..forensic.signals import TokenProfile
from ..risk import HIGH_THRESHOLD, Verdict
from .serialize import draft_to_dict, verdict_to_dict
```

Then:

```python
def assess_and_act(
    memory: ForensicMemory,
    alerts: AlertStore,
    build_profile: Callable[[str], TokenProfile],
    mint: str,
    now: str,
    *,
    as_of: str | None = None,
) -> dict:
    """Assess a mint, and if the verdict is HIGH, auto-watchlist its deployer and draft a
    pending alert. The verdict (the valuable read) is ALWAYS returned; a failed write
    degrades to acted=False + an `error` note rather than discarding the investigation."""
    profile = build_profile(mint)
    verdict = assess_risk(profile, memory, as_of=as_of)
    result = verdict_to_dict(verdict)
    result["acted"] = False
    result["watchlisted"] = None
    result["alert"] = None
    if verdict.score >= HIGH_THRESHOLD and profile.deployer:
        try:
            edge = watchlist_add(memory, profile.deployer, mint, verdict.score, now)
            draft = draft_alert(alerts, verdict, profile.deployer, mint, now)
            result["acted"] = True
            result["watchlisted"] = {
                "deployer": profile.deployer, "mint": mint, "edge_id": edge.id
            }
            result["alert"] = draft_to_dict(draft)
        except Exception as exc:  # keep the verdict; surface only the failure type
            result["error"] = f"act failed: {type(exc).__name__}"
    return result
```

- [ ] **Step 4: Run, verify pass + full suite**

Run: `pytest tests/test_actions.py -q` → PASS
Run: `pytest -q` → PASS (no regressions)
Run: `ruff check src/anamnesis/agent/actions.py tests/test_actions.py` → clean

- [ ] **Step 5: Commit**

```bash
git add src/anamnesis/agent/actions.py tests/test_actions.py
git commit -S -m "feat: assess_and_act — auto watchlist + draft at HIGH (B.1 DoD)"
```

---

### Task 7: `list_pending_alerts` + explicit-tool handlers (`watchlist_mint`, `draft_for_mint`)

**Files:**
- Modify: `src/anamnesis/agent/actions.py` (append)
- Test: `tests/test_actions.py` (append)

**Interfaces:**
- Produces:
  - `list_pending_alerts(alerts:AlertStore) -> dict` → `{"pending": [draft dicts], "count": int}`
  - `watchlist_mint(memory, build_profile, mint, now) -> dict` → assesses the mint, force-watchlists its deployer; `{"watchlisted": {...}|None, "note"?: str}`
  - `draft_for_mint(memory, alerts, build_profile, mint, now) -> dict` → assesses the mint, drafts an alert regardless of threshold; `{"alert": {...}|None, "note"?: str}`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_actions.py`:

```python
from anamnesis.agent.actions import draft_for_mint, list_pending_alerts, watchlist_mint


def test_list_pending_alerts_returns_queue():
    store = InMemoryAlertStore()
    draft_alert(store, _verdict(), "dep", "mintZ", "2026-06-27")
    out = list_pending_alerts(store)
    assert out["count"] == 1
    assert out["pending"][0]["mint"] == "mintZ" and out["pending"][0]["status"] == "pending"


def test_watchlist_mint_forces_watchlist_even_when_low():
    mem = ForensicMemory(InMemoryRepository())
    out = watchlist_mint(mem, lambda m: _clean_profile("freshWallet", "m"), "m", "2026-06-27")
    assert out["watchlisted"]["deployer"] == "freshWallet"
    assert [e for e in mem.recall("freshWallet") if e.type == "WATCHLISTED"]


def test_watchlist_mint_unresolved_deployer_is_a_noop():
    mem = ForensicMemory(InMemoryRepository())
    out = watchlist_mint(mem, lambda m: _clean_profile(None, "m"), "m", "2026-06-27")
    assert out["watchlisted"] is None and "note" in out


def test_draft_for_mint_drafts_regardless_of_threshold():
    mem, store = ForensicMemory(InMemoryRepository()), InMemoryAlertStore()
    out = draft_for_mint(mem, store, lambda m: _clean_profile("freshWallet", "m"), "m", "2026-06-27")
    assert out["alert"]["mint"] == "m" and out["alert"]["status"] == "pending"
    assert len(store.list_pending()) == 1
```

- [ ] **Step 2: Run, verify failure**

Run: `pytest tests/test_actions.py -q`
Expected: FAIL — `ImportError: cannot import name 'list_pending_alerts'`.

- [ ] **Step 3: Implement (append to `agent/actions.py`)**

```python
def list_pending_alerts(alerts: AlertStore) -> dict:
    """The human-in-the-loop review surface: every pending (un-sent) alert draft."""
    pending = alerts.list_pending()
    return {"pending": [draft_to_dict(d) for d in pending], "count": len(pending)}


def watchlist_mint(
    memory: ForensicMemory, build_profile: Callable[[str], TokenProfile], mint: str, now: str
) -> dict:
    """Explicit watchlist: assess the mint and force-watchlist its deployer (no threshold),
    carrying the derived risk score. A no-op with a note when the deployer is unresolved."""
    profile = build_profile(mint)
    if not profile.deployer:
        return {"watchlisted": None, "note": "deployer unresolved; nothing to watchlist"}
    verdict = assess_risk(profile, memory)
    edge = watchlist_add(memory, profile.deployer, mint, verdict.score, now)
    return {"watchlisted": {"deployer": profile.deployer, "mint": mint, "edge_id": edge.id}}


def draft_for_mint(
    memory: ForensicMemory,
    alerts: AlertStore,
    build_profile: Callable[[str], TokenProfile],
    mint: str,
    now: str,
) -> dict:
    """Explicit draft: assess the mint and draft a pending alert regardless of threshold.
    A no-op with a note when the deployer is unresolved."""
    profile = build_profile(mint)
    if not profile.deployer:
        return {"alert": None, "note": "deployer unresolved; cannot draft"}
    verdict = assess_risk(profile, memory)
    draft = draft_alert(alerts, verdict, profile.deployer, mint, now)
    return {"alert": draft_to_dict(draft)}
```

- [ ] **Step 4: Run, verify pass**

Run: `pytest tests/test_actions.py -q` → PASS
Run: `ruff check src/anamnesis/agent/actions.py tests/test_actions.py` → clean

- [ ] **Step 5: Commit**

```bash
git add src/anamnesis/agent/actions.py tests/test_actions.py
git commit -S -m "feat: list_pending_alerts + explicit watchlist_mint/draft_for_mint handlers"
```

---

### Task 8: native `@register_tool` wrappers + agent wiring + models doc

**Files:**
- Modify: `src/anamnesis/agent/tools.py` (shared `_client()`, `_alerts()` singleton, upgrade `AssessRiskTool`, add 3 tool classes)
- Modify: `src/anamnesis/agent/agent.py` (`build_function_list` — add the 3 new tool names)
- Modify: `src/anamnesis/memory/models.py` (document `WATCHLISTED` in the `Edge.type` comment)
- Test: `tests/test_agent_tool_registration.py` (add assertions; CI-skipped via `importorskip`)

**Interfaces:**
- Consumes: Task 4-7 functions; existing singletons (`_memory`, `_helius`, `_dex`, `_now`, `_args`).
- Produces: registered tools `watchlist_add`, `draft_alert`, `list_pending_alerts`; `assess_risk` upgraded to auto-act; a shared `_client()` so memory + alerts share one Mongo connection.

- [ ] **Step 1: Write the failing test**

Read `tests/test_agent_tool_registration.py` first to match its existing `importorskip` pattern, then append:

```python
def test_acts_tools_are_registered():
    pytest.importorskip("qwen_agent")
    from qwen_agent.tools.base import TOOL_REGISTRY

    import anamnesis.agent.tools  # noqa: F401 — fires the @register_tool decorators

    for name in ("watchlist_add", "draft_alert", "list_pending_alerts"):
        assert name in TOOL_REGISTRY
```

(If the file lacks `import pytest`, add it.)

- [ ] **Step 2: Run, verify failure**

Run: `pytest tests/test_agent_tool_registration.py -q`
Expected: in a qwen-agent env, FAIL (`watchlist_add` not in registry); in CI, SKIP. Either is acceptable to proceed — implement next.

- [ ] **Step 3a: Add the shared client + alerts singleton in `tools.py`**

Inside the `if register_tool is not None:` block, replace the body of `_memory()` to use a shared client and add `_alerts()` (place after `_memory`):

```python
    _client_singleton = None  # add near the other singletons

    def _client():
        global _client_singleton
        if _client_singleton is None:
            from pymongo import MongoClient

            _client_singleton = MongoClient(config.require("ANAMNESIS_MONGODB_URI"))
        return _client_singleton

    def _memory() -> ForensicMemory:
        global _memory_singleton
        if _memory_singleton is None:
            _memory_singleton = ForensicMemory(MongoRepository(_client(), config.ANAMNESIS_DB))
        return _memory_singleton

    _alerts_singleton = None

    def _alerts():
        global _alerts_singleton
        if _alerts_singleton is None:
            from ..memory.alerts import MongoAlertStore

            _alerts_singleton = MongoAlertStore(_client(), config.ANAMNESIS_DB)
        return _alerts_singleton
```

Add to the module imports near the top: `from .actions import (assess_and_act, draft_for_mint, list_pending_alerts, watchlist_mint)`.

- [ ] **Step 3b: Upgrade `AssessRiskTool.call` to auto-act**

Replace its `call` body with:

```python
        def call(self, params, **kwargs) -> str:
            a = _args(params)
            return json.dumps(assess_and_act(
                _memory(), _alerts(),
                lambda m: build_lp_aware_profile(_helius(), _dex(), m),
                a["mint"], _now(), as_of=a.get("as_of"),
            ))
```

Append to its `description`: `" When risk is HIGH it auto-watchlists the deployer and drafts a pending alert (never sent)."`

- [ ] **Step 3c: Add the three new tool classes** (after `AssessRiskTool`, inside the same block)

```python
    @register_tool("watchlist_add")
    class WatchlistAddTool(BaseTool):
        description = ("Watchlist a token's deployer so every FUTURE token they launch is "
                       "flagged on sight. Records a provenance-tracked memory edge.")
        parameters = [{"name": "mint", "type": "string", "required": True,
                       "description": "The mint whose deployer to watchlist."}]

        def call(self, params, **kwargs) -> str:
            a = _args(params)
            return json.dumps(watchlist_mint(
                _memory(), lambda m: build_lp_aware_profile(_helius(), _dex(), m),
                a["mint"], _now(),
            ))

    @register_tool("draft_alert")
    class DraftAlertTool(BaseTool):
        description = ("Draft a human-reviewable alert for a token (status=pending; never "
                       "auto-sent). A human reviews and decides via list_pending_alerts.")
        parameters = [{"name": "mint", "type": "string", "required": True,
                       "description": "The mint to draft an alert for."}]

        def call(self, params, **kwargs) -> str:
            a = _args(params)
            return json.dumps(draft_for_mint(
                _memory(), _alerts(), lambda m: build_lp_aware_profile(_helius(), _dex(), m),
                a["mint"], _now(),
            ))

    @register_tool("list_pending_alerts")
    class ListPendingAlertsTool(BaseTool):
        description = ("List all pending (un-sent) alert drafts the agent's memory has "
                       "auto-drafted — the human-in-the-loop review queue.")
        parameters = []

        def call(self, params, **kwargs) -> str:
            return json.dumps(list_pending_alerts(_alerts()))
```

- [ ] **Step 3d: Wire the tool names into `agent/agent.py`**

Read `build_function_list` in `src/anamnesis/agent/agent.py`; add the three names to the returned native-tool list so it ends with: `"recall", "remember", "assess_risk", "watchlist_add", "draft_alert", "list_pending_alerts"`.

- [ ] **Step 3e: Document `WATCHLISTED` in `memory/models.py`**

Update the `Edge.type` comment (line ~24) to include the new type:

```python
    type: str  # DEPLOYED | FUNDED_BY | PROVIDES_LP | SAME_CLUSTER | RUGGED | WATCHLISTED
```

- [ ] **Step 4: Run, verify**

Run: `pytest -q` → PASS (registration test SKIPS in CI without qwen-agent; full pure suite green)
Run: `ruff check src tests` → clean
If qwen-agent is installed locally: `pytest tests/test_agent_tool_registration.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/anamnesis/agent/tools.py src/anamnesis/agent/agent.py src/anamnesis/memory/models.py tests/test_agent_tool_registration.py
git commit -S -m "feat: wire watchlist/draft/list tools + auto-acting assess_risk into the agent"
```

---

## Final verification (after all tasks)

- [ ] `pytest -q` → all green (in-memory)
- [ ] `pytest -q --store=mongo` → all green (mongomock)
- [ ] `ruff check src tests` → clean
- [ ] `git log --oneline main..HEAD` shows 8 focused, signed commits
- [ ] Open a PR `feat/b1-memoryagent-acts` → `main`; CI green; merge `--merge --delete-branch`.

## Spec coverage map

| Spec section | Task |
|---|---|
| AlertDraft + AlertStore (D3) | 1, 2 |
| Watchlist = WATCHLISTED edge, deployer→mint, derived (D3, D4) | 4 |
| No feedback loop (D6) | 4 (test) |
| draft_alert pending + idempotent (D3, D7) | 5 |
| Deterministic auto-trigger at HIGH (D2) | 6 |
| Error degradation, verdict preserved (D8) | 6 |
| list_pending_alerts (human-in-loop) + explicit tools | 7 |
| Tool surface + agent wiring + assess_risk upgrade (D2, D5) | 8 |
| Pure core unchanged / CI-testable (D5) | all (pure modules; wrappers CI-skipped) |
