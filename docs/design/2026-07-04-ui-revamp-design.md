# Anamnesis — UI Revamp Design Spec

**Date:** 2026-07-04 · **Track:** MemoryAgent · **Deadline:** Jul 9 2026 2:00pm PDT (build-ready target **~Jul 8**) · **Mode:** all-in (the modern UI *is* the submission demo; Gradio remains a physical last-resort only)

## 1. Goal

Replace Qwen-Agent's default Gradio WebUI with a modern **forensic-intelligence dashboard** that makes the *compounding-memory* thesis **undeniable, quantified, and visible** — the exact lever the track research identified to offset MemoryAgent's demo-ability disadvantage. The AI/forensic engine is untouched; only the presentation layer + a thin API are new.

## 2. Constraints (non-negotiable)

- **Backend stays on Alibaba ECS** (hard hackathon requirement: "backend running on Alibaba Cloud").
- **The forensic engine is frozen** — `src/anamnesis/**` (signals, risk, memory, LP, assess) and `mcp/` are NOT modified. We ADD an API layer + a frontend; we do not touch memory/scoring/MCP logic.
- **Deps pinned** (`qwen-agent==0.0.34`, `mcp==1.12.4`).
- **Lead with memory, keep autopilot a supporting beat** (per TRACK-DECISION.md — no track-drift).

## 3. Scope

**IN (frozen set — mockup v4 + sparkline):**
- One **verdict dashboard**, **Lite (default) ⇄ Pro** toggle (progressive disclosure, one component set).
- Search (paste a mint) → live agent scan → verdict.
- Cards: **verdict** (level/score/mint/⚡memory-flag/provenance tiers), **compounding-memory band** (99,313× · MED→HIGH-across-sessions · compounds), **evidence** (memory rugs + live signals + holder bar), **token profile**, **deployer 13-token history**, **cluster graph**, **funding trail**, **autopilot actions**, **follow-up chat** (streaming), **tooltips** (ⓘ), **minimal price sparkline** (secondary, under the verdict).
- Forensic-premium dark aesthetic; orchestrated entrance animation (score count-up, stripe draw, graph edge-trace, staggered cards).

**OUT (post-hackathon v2):** landing page, multi-page nav, session/history browser, full price/trading chart, auth/accounts, deep mobile polish beyond responsive.

## 4. Architecture

**Frontend (new):** Vite + React + TypeScript + Tailwind + **shadcn/ui** + **Framer Motion**. Static SPA (no SSR needed — it's a client hitting the agent API). Cluster graph rendered client-side from graph JSON (`react-force-graph-2d` or lean custom canvas; fallback = embed the existing `/graphs` SVG). Sparkline = tiny inline SVG from DexScreener points.

**Backend API (new, thin) — FastAPI wrapping the existing engine:**
| Endpoint | Purpose |
|---|---|
| `POST /api/assess` | Runs `assess_and_act(mint)` → **structured verdict JSON** (level, score, provenance tiers, signals, memory rugs, deployer 13-token profile, actions) for the cards |
| `POST /api/chat` (SSE) | The conversational agent for follow-ups — streams the tool-trace + answer |
| `GET /api/graph/{deployer}` | Cluster-graph nodes/edges JSON (or reuse existing render) |
| `GET /api/price/{mint}` | Sparkline points (DexScreener — client already used for LP) |

The API is a **serialization + transport shell** over the frozen engine — zero forensic logic duplicated. `assess_and_act` already returns a structured dict; we extend `serialize.py` to include everything the cards need.

**Hosting (recommended):** **everything on the Alibaba ECS** — nginx serves the static frontend build + proxies `/api` → FastAPI (uvicorn) + `/graphs`. Airtight "backend on Alibaba" story, no cross-origin, one box, one deploy.
- *Alternative (needs confirm):* frontend on **Vercel** (free, per the global deploy preference) + API on Alibaba. Rejected for the 5-day all-in: adds cross-origin (CORS), a second platform, and muddies the "on Alibaba" demo. **Decision to confirm in review.**

## 5. Data flow

`paste mint → POST /api/assess → structured verdict → render cards` (Lite: verdict + band + graph + sparkline; Pro: all) `→ follow-ups via POST /api/chat (SSE) → graph & price lazy-loaded.`

## 6. States (must all be handled)

- **Scanning** (~20–40s live reads): scan-line + "reading on-chain…" + skeleton cards (this narrates the wait — fixes finding T6).
- **Invalid mint:** graceful "not a valid Solana public key" (engine already returns this).
- **Partial/mega-cap degrade:** render available data with `UNVERIFIED` chips; never crash.
- **API/network error:** inline, actionable, retryable.

## 7. Testing

- **API:** pytest on the FastAPI endpoints (structured-assess shape, chat SSE, error paths) reusing the engine's fixtures (mongomock + stub profiles). Engine tests stay green (236).
- **Frontend:** Vitest + Testing Library (verdict card renders a verdict; Lite/Pro toggle hides/shows; tooltip a11y; loading/error states).
- **E2E smoke:** the hero flow (paste GYaS → HIGH-from-memory) against the real API, driven via Chrome MCP.

## 8. Timeline (all-in → ~Jul 8)

1. **API + serialization** (structured assess, chat SSE, graph, price) + **scaffold** Vite/React/shadcn. ← trickiest; do first.
2. **Dashboard** built against the API (cards, Lite/Pro, band, tooltips, sparkline) + animation.
3. **Cluster graph + streaming chat** + polish + all states.
4. **Deploy to ECS** (nginx static + `/api`), end-to-end test, **record**.

**#1 hard dependency:** the ECS must be live → **add the payment method today** (do not wait on Elvin).

## 9. Risks

- **ECS gated on payment** — the single biggest risk; unblock today.
- **Agent-as-API seam** (streaming + structured output) is the riskiest new code — build + test Day 1.
- **No fallback chosen** (all-in); Gradio remains a physical last resort only.
- **Scope is frozen** at v4 + sparkline — further additions endanger Jul 8.

## 10. Reference

Mockup (v4, live): the forensic-premium dashboard with Lite⇄Pro. Track rationale: `~/Documents/secret/strategy/anamnesis/TRACK-DECISION.md`. Deploy mechanics: `deploy/RUNBOOK.md` + the pre-filled command-sheet.
