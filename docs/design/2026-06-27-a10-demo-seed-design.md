# A.10 — Demo seed (`scripts/seed_demo.py`) — Design

**Date:** 2026-06-27
**Status:** Approved (anchor + mechanic confirmed)
**Phase:** A.10 (submission packaging — Phase A/B feature-frozen; this is demo tooling, not new agent capability)

## Goal

Make the demo's hero moment reproducible: a **brand-new, clean-looking token from a known serial
rugger is flagged HIGH from memory alone**, the relationship graph lights up with the deployer's
prior rugs, and we can quote an honest "N× faster than re-deriving it cold" number. The seed writes
a real serial rugger's prior-rug history into memory so the live agent, run against another real
token by that deployer, fuses that history into a HIGH verdict.

## Why a seed is needed (the mechanic)

`assess_risk(mint)` → `build_token_profile(mint)` runs a live `resolve_origin` to get the mint's
**deployer**, then `compose_verdict` lets the deployer's *remembered* `RUGGED` history drive the
score even when the token's own live signals are clean (`risk.py`: `score = max(live, memory_risk)`;
`memory_risk ≥ 0.6 → HIGH`). The scorer (`memory/graph.py`) is tuned (`PER_FACT_SCALE = 0.47`) so:

- 1 distinct first-party `RUGGED` edge → `1 − (1−0.47)` = **0.47 → MEDIUM**
- 2 distinct → `1 − 0.53²` = **0.72 → HIGH** ("serial rugger on sight")
- 3 distinct → `1 − 0.53³` = **0.85 → HIGH** (decisive; richer cluster graph)

Two hard constraints this imposes:
1. The demo's live token **must be a real on-chain mint whose `resolve_origin` returns the seeded
   deployer** — a synthetic mint resolves to nothing, so the fusion never fires.
2. The rug edges must be **`first_party`** to score. The agent's `remember` tool *forces*
   `method="claimed"` (poisoning defense), so the seed writes edges **directly via
   `ForensicMemory.remember()`** — legitimately simulating the agent's own grounded observations
   from prior sessions (`make_edge`'s docstring already names "demo seed" as an intended writer).

## The anchor (real, found via Helius)

Deployer **`sF2wwbFkuzD9mT6YfwXmLE14qyzJVaf2QEDg8dZkMvv`** — 13 real mints launched Nov 2025 →
2026-06-27, nearly all dead / zero-liquidity. Verified live: its newest token resolves to it in
~1.7s.

| Role | Mint | Note |
|---|---|---|
| **Demo "4th" (assessed live)** | `GYaS5YyD9jMGSFAFA7Q9MCCpcUpmf3YtutEDrZRpump` | created 2026-06-27; **scores LOW (0.2) on its own live signals** (renounced authorities) — the exact "looks clean" contrast. NOT seeded. |
| Prior rug 1 | `A1473c8sov1uue8KAjMCHZGRgnDQYn6UJbY33p1ipump` | 2025-12-05, dead |
| Prior rug 2 | `258YRv1dTEEYAxQFJkXuLJ5zYVKjG1SJA5ueeCqvpump` | 2025-11-20, dead |
| Prior rug 3 | `3qFSoG3TcNs8QhcgBe5Ra3UgsLWd2k9QZXfs1KY3pump` | 2025-11-16, dead |

Constants live at the top of `seed_demo.py` for one-line edits if a mint's state drifts.

## What the seed writes

For each prior-rug mint `R`, via `ForensicMemory.remember([...], now)`:

- `DEPLOYED` edge — `src=deployer, dst=R, type="DEPLOYED"` — recalled context, does not score.
- `RUGGED` edge — `src=deployer, dst=R, type="RUGGED"`, `provenance=Provenance(source="seed:prior-session-observation", method="first_party", confidence=1.0)`.

**Bi-temporal split** (the compounding-memory story, made literal):
- `valid_from` = the token's real on-chain creation date (2025) — when the rug was true on-chain.
- `recorded_at` = staggered fixed past-session dates this month (e.g. 2026-06-05 / -15 / -22) —
  when "the agent" logged each rug. This yields a free **as-of/time-travel** beat: recall as-of
  2026-06-10 surfaces only rug 1; as-of now, all three.

**Idempotency:** `make_edge` ids are deterministic (`type:src->dst@recorded_at#method:source`). With
fixed-constant `recorded_at`, re-running upserts the same ids → no duplicates. Safe to re-run before
each take.

**Reset (opt-in, two-step):** default is upsert-only. `--reset` *previews* the destructive action —
it prints the target DB + host + current counts and exits non-zero; only `--reset --force` actually
clears the `relations` + `alert_drafts` collections (never drops the DB, never touches any other
collection). The safety is this explicit, target-visible confirmation, **not** a DB-name blocklist:
dev and the deployed instance share the DB name `anamnesis` (config default), so a name guard cannot
tell them apart and only gives false confidence (caught in review).

Target DB is whatever `ANAMNESIS_MONGODB_URI` points at — dev Mongo now, Alibaba at deploy time.

## N× metric (`--metric`, honest + measurable)

Question measured: *"has this deployer rugged before?"*
- **Memory path:** `recall_deployer_history(deployer)` + `trust_weighted_risk` — one indexed Mongo
  query. Sub-millisecond to low-ms.
- **Cold path:** `get_deployer_token_history(deployer)` (scan the deployer's signatures for created
  mints) + `build_token_profile` on each prior mint to re-derive that it rugged — seconds (N mints ×
  multi-RPC).
- Report `N× = cold_wall_time / memory_wall_time`, measured against this real deployer, plus the raw
  times. This is the number for the video + README.

## `app.py` change

Swap the seeded demo mint into `CHATBOT_CONFIG["prompt.suggestions"]`, e.g.
`"Should I ape this token? GYaS5YyD9jMGSFAFA7Q9MCCpcUpmf3YtutEDrZRpump"`, so the judged WebUI opens
one click away from the hero flow. (Per the native-tool test note, this is a config-only change — no
tool-list change, so no `test_agent_assembly` assertion update.)

## Testing (TDD, no live services)

The pure core is a function `build_seed_edges(deployer, rugs, ...) -> list[Edge]`; the I/O shell
writes them and (optionally) measures. Tests use `mongomock` (matching the suite):
1. `build_seed_edges` emits, per rug, a first-party `RUGGED` + a `DEPLOYED` edge with correct
   `src/dst/type/method` and the bi-temporal split.
2. Feeding the edges through `ForensicMemory` (mongomock) → `recall_deployer_history(deployer)` →
   `trust_weighted_risk` **≥ 0.6** (HIGH) for the 3-rug seed; and that 2 distinct rugs already clear
   0.6 (pins the tuning the demo depends on).
3. Idempotency: seeding twice yields no duplicate edges (deterministic ids).
4. `--reset` guard: refuses a prod-like DB name.

`seed_demo.py` must import without qwen-agent/mcp/openai (pure `memory` + `forensic` deps only), per
the CI-subset rule.

## Reliability for the recorded video

- HIGH is driven by the **seeded memory**, so it fires regardless of the demo mint's live drift at
  record time; only the secondary "live signals" line could change.
- Deterministic + idempotent + `--reset` → pristine, repeatable state per take.
- The demo mint resolves in one page (~1.7s).
- Suppress qwen-agent's `httpx` INFO logging before recording (it echoes the Helius api-key in the
  request URL — cosmetic key-leak in the console, not our scrubbed error path).

## Non-goals

- No new agent tools or scorer changes (feature freeze).
- No synthetic/mocked on-chain reads — the demo is a real forensic run over real mainnet state.
- Not a general fixtures framework — one curated, approved anchor.
