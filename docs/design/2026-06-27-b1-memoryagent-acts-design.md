# B.1 — MemoryAgent that acts: `watchlist_add` + `draft_alert` (design)

- **Date:** 2026-06-27
- **Status:** Approved — ready for implementation plan
- **Task:** SPEC Phase B — "MemoryAgent that acts" (the acts half; the relationship-graph view is deferred to **B.2**)
- **Depends on:** `memory/models.py` + `memory/repository.py` + `memory/graph.py` (A.6 — `Edge`, `Provenance`, `Repository`, `ForensicMemory.remember/recall`), `risk.py` + `assess.py` (A.7 — `Verdict`, `assess_risk`, `HIGH_THRESHOLD`), `agent/tools.py` + `agent/agent.py` (A.9 — native `@register_tool` wrappers, `function_list`, singletons)

## Goal

Make the agent **act** on a high-risk verdict instead of only reporting it. When `assess_risk` produces a verdict with **score ≥ `HIGH_THRESHOLD` (0.6)**, the system automatically:

1. **Watchlists the deployer** — records a `WATCHLISTED` edge so every *future* token from that wallet is flagged on sight (the compounding-memory thesis applied to action, not just recall).
2. **Drafts a human-readable alert** — a structured, rendered message persisted to a pending queue. The draft is **never sent** — a human reviews and decides (human-in-the-loop). Sending is a non-goal.

**DoD (from SPEC):** a remembered repeat offender, re-assessed on a brand-new token, auto-drafts an alert; the watchlist and the pending-alert queue are inspectable.

The relationship-graph view ("graph lights up the cluster") is a distinct visual concern requiring new multi-hop traversal and a UI surface — split into **B.2** so this spec stays a tight, shippable action layer.

## Decisions

### D1 — Scope: the acts only; graph view → B.2

`watchlist_add` and `draft_alert` are tightly coupled (the alert drafts off the verdict that also drives the watchlist). The graph view is independent (traversal + visualization, no shared logic). Bundling it would mix data/tool work with a UI build and enlarge the plan. B.1 ships the acts; B.2 is its own spec → plan → cycle.

### D2 — Trigger: deterministic auto at HIGH, in the acts layer (not in the pure verdict)

SPEC says *"threshold-triggered ... auto-drafts an alert"* — so acting is **deterministic**, not left to LLM discretion (which might silently not fire and can't be demoed reliably). The trigger is a single threshold: `verdict.score >= HIGH_THRESHOLD (0.6)` → watchlist + draft. MEDIUM does nothing in B.1 (YAGNI; the band is trivial to extend later).

`assess.py::assess_risk` stays **pure** (verdict only, no writes) — its purity and unit tests are preserved. The auto-trigger lives in a new orchestrator (`assess_and_act`) at the tool boundary, which calls `assess_risk` then performs the writes. The agent's `assess_risk` *tool* is upgraded to call the orchestrator, so the one-call investigate → verdict → act flow the demo needs is intact, while the pure decision function is untouched.

### D3 — Persistence: `WATCHLISTED` edge (in memory) + an `alert_drafts` queue (new store)

- **Watchlist** is modelled as a **new edge type in the existing bi-temporal memory** — it reuses `Edge`/`Provenance`, the `Repository` (InMemory + Mongo), `recall`, as-of time-travel, and supersession for free. A watchlist entry is a provenance-bearing fact ("we derived, on date T, that this deployer is high-risk"), which is exactly what an edge is.
- **Alert drafts** carry a payload (rendered message, severity, evidence, status) that does not fit the fixed `Edge` shape, so they live in a **separate store** (`AlertStore`) mirroring the `Repository` pattern — protocol + `InMemoryAlertStore` (test fake) + `MongoAlertStore` (collection `alert_drafts` in `config.ANAMNESIS_DB`). A persisted queue makes "human-in-the-loop" concrete (a reviewable list) and demos well.

### D4 — Watchlist subject: the deployer, triggered by the mint

The edge is `WATCHLISTED: src=deployer → dst=triggering_mint`. The **deployer** is the watched entity (so the next token they launch auto-flags via memory — the whole point of compounding memory); the **mint** is recorded as the triggering context. `recall(deployer)` surfaces the watchlist; the mint is not separately watchlisted (avoids redundant records).

### D5 — Structure: a thin acts layer over the pure core

New, well-bounded units; the pure verdict + memory modules are untouched in behaviour:

- `memory/alerts.py` — `AlertDraft`, `AlertStore` protocol, `InMemoryAlertStore`, `MongoAlertStore`.
- `agent/actions.py` — pure functions: `watchlist_add`, `draft_alert`, `assess_and_act`, `list_pending_alerts`.
- `agent/tools.py` — new `@register_tool` wrappers + an upgraded `assess_risk`; a new `_alerts_singleton`.

### D6 — Integrity: watchlisting must not create a risk feedback loop

`WATCHLISTED` is deliberately **absent from `TYPE_CEILING`** (`graph.py`), so `trust_weighted_risk` never scores it, and `recall_deployer_history` already filters to `DEPLOYED`/`RUGGED` only. The watchlist is therefore recall-able and visible but **cannot inflate a future verdict** — preventing the loop where "we watchlisted them" becomes self-reinforcing evidence. The `WATCHLISTED` edge's provenance is `method="derived"` (it is derived from the verdict, not a first-party on-chain observation), consistent with this.

### D7 — Human-in-the-loop: pending-only drafts, idempotent, with a review tool

- Drafts are created with `status="pending"` and are **never auto-`sent`** (sending is a non-goal; the `status` field leaves room for a future send/dismiss lifecycle).
- **Idempotent:** re-assessing the same `(deployer, mint)` **supersedes** the `WATCHLISTED` edge (bi-temporal, by method-rank — no duplicate) and **reuses** the existing pending draft for that pair (no alert spam). `draft_alert` returns the existing pending draft if one already exists.
- `list_pending_alerts` exposes the queue so a human (or the agent) can review what memory has auto-drafted.

### D8 — Error handling: a failed act must not lose the verdict

The verdict (the valuable read) is always returned. If a write fails (`remember` is already all-or-nothing; `add_draft` likewise), `assess_and_act` degrades to `acted: false` with an `error` note rather than raising — the investigation result is never discarded because a side-effect write failed. No new external/network I/O is introduced; acts touch only Mongo.

## Data model

**New edge type** (`type` is a free-form string today, so no enum change — only docs/usage):

```
WATCHLISTED   src=deployer  dst=triggering_mint
              provenance = Provenance(source="assess_risk", method="derived", confidence=verdict.score)
              valid_from = recorded_at = now ; superseded on re-assess by method-rank
```

**New artifact** (`memory/alerts.py`):

```python
@dataclass(frozen=True)
class AlertDraft:
    id: str            # deterministic: f"alert:{deployer}->{mint}@{created_at}"
    deployer: str
    mint: str
    severity: str      # = verdict.level (e.g. "high")
    score: float       # verdict.score
    rationale: str     # verdict.rationale
    evidence: list[str]  # human-readable lines from cited_signals + remembered edges
    message: str       # fully rendered, human-readable alert text
    status: str        # "pending" (never auto-"sent")
    created_at: str    # ISO-8601 UTC
```

## Components & signatures

```python
# memory/alerts.py
class AlertStore(Protocol):
    def add_draft(self, draft: AlertDraft) -> AlertDraft: ...   # idempotent per (deployer, mint) pending
    def list_pending(self) -> list[AlertDraft]: ...
    def get(self, draft_id: str) -> AlertDraft | None: ...

class InMemoryAlertStore: ...      # test fake
class MongoAlertStore: ...         # collection "alert_drafts" in config.ANAMNESIS_DB

# agent/actions.py  (all pure, CI-testable with fakes)
def watchlist_add(memory, deployer: str, mint: str, score: float, now: str) -> Edge | None
def draft_alert(alerts, verdict, deployer: str, mint: str, now: str) -> AlertDraft
def assess_and_act(memory, alerts, build_profile, mint: str, now: str, as_of=None) -> dict
    # -> {level, score, rationale, signals, remembered, acted: bool,
    #     watchlisted: {...}|None, alert: {...}|None, error?: str}
def list_pending_alerts(alerts) -> dict   # -> {pending: [ {AlertDraft...} ], count}
```

## Tool surface (native `@register_tool`, mirroring existing handlers)

| Tool | Behaviour |
|------|-----------|
| `assess_risk` | **Upgraded** → runs `assess_and_act`; returns the verdict plus `{acted, watchlisted, alert}`. Auto-acts at HIGH. |
| `watchlist_add` | Explicit: watchlist a deployer (manual/agent-initiated) for a given mint; derives the risk score via `assess_risk` so the edge carries a real `confidence`. |
| `draft_alert` | Explicit: draft an alert for a given mint from its current verdict. |
| `list_pending_alerts` | Review the pending-draft queue (the human-in-the-loop surface). |

All four are wired into `agent.py::build_function_list` and back the pure handlers in `agent/actions.py`. A new `_alerts_singleton` (a `MongoAlertStore`) is lazily initialised alongside `_memory_singleton`, sharing the same Mongo client/db.

## Testing

Pure unit + contract tests, CI-runnable (mongomock + InMemory; no qwen-agent/mcp needed):

- **watchlist_add:** writes a `WATCHLISTED` edge with `method="derived"` + `confidence=score`; re-add supersedes (no dup); `recall(deployer)` surfaces it; **`trust_weighted_risk` ignores it** (no feedback loop) — assert a watchlisted deployer with no `RUGGED` history still scores 0 from memory.
- **draft_alert:** renders the correct draft from a `Verdict` (severity=level, evidence from signals + remembered); persists `pending`; **idempotent** per `(deployer, mint)`.
- **assess_and_act:** HIGH verdict → `acted: true` + watchlist + alert; LOW/MEDIUM → `acted: false`, no writes; **DoD test** — a serial rugger (remembered `RUGGED` history) on a fresh mint → verdict HIGH → alert drafted.
- **assess_and_act error path:** a failing store degrades to `acted: false` + `error`, verdict still returned.
- **AlertStore contract:** `add_draft`/`list_pending`/`get` + idempotency, run against **both** `InMemoryAlertStore` and `MongoAlertStore` (extend the `conftest.py` `--store` pattern with an `alerts` fixture).
- **Tool registration** (`@register_tool` wrappers): CI-skipped via `importorskip`, as with existing native tools.

## File plan

**New:**
- `src/anamnesis/memory/alerts.py` — `AlertDraft`, `AlertStore`, `InMemoryAlertStore`, `MongoAlertStore`.
- `src/anamnesis/agent/actions.py` — `watchlist_add`, `draft_alert`, `assess_and_act`, `list_pending_alerts`.
- `tests/test_actions.py`, `tests/test_alerts_store.py`.

**Modified:**
- `src/anamnesis/agent/tools.py` — add `WatchlistAdd` / `DraftAlert` / `ListPendingAlerts` `@register_tool` wrappers; upgrade `AssessRisk` to call `assess_and_act`; add `_alerts_singleton`.
- `src/anamnesis/agent/agent.py` — add the three new tool names to `build_function_list`.
- `src/anamnesis/memory/models.py` — document `WATCHLISTED` in the edge-type list/docstring.
- `tests/conftest.py` — `alerts` fixture mirroring the `repo` fixture.

## Out of scope (B.1) / forward contract

- **B.2 — relationship-graph view:** multi-hop cluster traversal (`recall_cluster(wallet, depth, rel_types=[SAME_CLUSTER, FUNDED_BY])`) + a visual surface. Not built here.
- **Sending alerts / send-dismiss lifecycle:** drafts stay `pending`; the `status` field reserves room.
- **MEDIUM-tier watchlisting** and a **notification daemon** (poll the `alert_drafts` queue): future, enabled by the persisted queue but not built.

## References

- `SPEC.md` §"Build phases" (Phase B) and §Non-goals ("Phase-B 'acts' = watchlist + drafted alert with human-in-the-loop, never an on-chain action").
- Prior art for structure: `docs/design/2026-06-25-a8b-funding-deployer-history-design.md` (pure-core + thin-tool pattern), `memory/graph.py` (trust-weighted scoring this design deliberately does not feed).
