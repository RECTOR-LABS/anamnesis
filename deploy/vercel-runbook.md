# Vercel deploy runbook — Anamnesis dashboard (serverless)

> Status: **plan + verified feasibility**. Not yet deployed — blocked on two provisioning gates
> (Pro tier, MongoDB Atlas) and one architectural decision (the `api/` naming collision, §4),
> then an empirical first-deploy to close the platform-specific unknowns (§6). The dashboard +
> agent run unchanged; this is a *deployment-target* change, not an engine change. The frozen
> engine (`src/anamnesis/**`, `mcp/**`) is untouched throughout.

## TL;DR — is Vercel viable?

**Yes — verified, not guessed.** The original "don't deploy to Vercel" verdict was based on a
~472 MB dep footprint and an assumed graph-FS blocker. Both turned out to be resolvable:

- **Size**: the bloat is `qwen-agent[gui]` (gradio 187 MB + modelscope 46 MB) which only the
  *legacy* chat WebUI (`app.py`) uses. The dashboard never imports it. Dropping `[gui]` (and
  `uvicorn` — Vercel is the ASGI server) measures **~175 MB** of site-packages, under Vercel's
  250 MB limit. The full serverless import chain (`api.main:app` + `build_agent`) loads cleanly
  without gradio/uvicorn. *(See §1.)*
- **Graph**: the dashboard's ClusterGraph tile is driven by the JSON route
  `/api/graph/{deployer}` (regenerated from memory each call), **not** the `/graphs/*.html`
  file. So it works serverless. Only the clickable `/graphs/*.html` link inside the agent's
  *chat reply* degrades (the rendered file isn't persistent across invocations) — a minor v1
  limitation, not a flagship break. *(See §3.)*

Two things genuinely need a real deploy to settle (can't be resolved by reading): whether SSE
streams on Vercel Python (§6.1), and whether the spawned MCP stdio-child behaves in the
function env (§6.2). Both have fallbacks.

## 0. Provisioning gates (RECTOR — do these first, in parallel)

1. **Vercel Pro tier** (`rz1989s`). Required for `maxDuration: 60` — the chat turn streams
   ~45 s (LLM + forensic-tool I/O); Hobby's 10 s cap will cut it off mid-turn. Pro is ~$20/mo.
2. **MongoDB Atlas M0 (free, 512 MB)** — the ECS self-hosted Mongo is gone. Create a free
   cluster, a DB user, and allow network access (Vercel egress IPs are dynamic; for a public
   demo either allow `0.0.0.0/0` or use Vercel's static IPs / Atlas's Vercel integration). Hand
   back the `mongodb+srv://...` URI. Then **re-seed the demo serial-rugger memory** into Atlas:
   `ANAMNESIS_MONGODB_URI=<atlas-uri> PYTHONPATH=src python scripts/seed_demo.py` (idempotent).

## 1. The serverless install (verified)

`requirements-vercel.txt` (repo root) is the slim set. The build installs it **plus** the
`anamnesis` package with `--no-deps` so it lands in site-packages without re-pulling `[gui]`:

```
pip install -r requirements-vercel.txt && pip install --no-deps .
```

`--no-deps .` is load-bearing: `pip install -e .` would follow `pyproject.toml`'s base
`dependencies` (`qwen-agent[gui,mcp]==0.0.34`) and drag gradio back in. `--no-deps` copies only
the `anamnesis` package into site-packages — which **both** the function **and** the spawned MCP
child need (the child is a fresh `sys.executable` process; it does not inherit the parent's
sys.path shim). *(The repo's `mcp/` dir does not shadow the pip `mcp` SDK: when the child runs
`mcp/solana_forensics_mcp.py`, sys.path[0] is the dir containing the script, so `import mcp`
resolves to the SDK in site-packages.)*

Measured: **~175 MB** site-packages (python 3.12, fresh venv). Under the 250 MB cap with room
for `src/` + `api/` + `mcp/` + the built SPA.

## 2. The architecture

- **SPA** (`frontend/dist`) → served as **Vercel static** (CDN). `outputDirectory: frontend/dist`.
- **API** → **one Python function** that exports the FastAPI ASGI app (`api.main:app`).
  Vercel's runtime detects `app` and serves it; a rewrite routes `/api/*` to it.
  `maxDuration: 60`, `memory: 1024`.
- **Env** (set on the Vercel project): `ANAMNESIS_DASHSCOPE_API_KEY`, `ANAMNESIS_HELIUS_API_KEY`,
  `ANAMNESIS_MONGODB_URI` (the Atlas URI). The MCP child gets the Helius key via its `env`
  block (not inheritance — see `anamnesis.agent.agent.build_function_list`).
- The FastAPI app's SPA mount (`api/main.py::_mount_frontend`) is a guarded no-op serverless
  (no `frontend/dist` in the function) — harmless; Vercel static serves the SPA instead.

## 3. The graph feature (downgraded, not broken)

- **Dashboard tile**: `GET /api/graph/{deployer}` → JSON `GraphData` (`api/routes/graph.py`),
  regenerated from memory via `recall_cluster` on every call. **Works serverless** — this is
  the primary visualization the dashboard shows.
- **Agent chat link**: the frozen `cluster_graph` tool renders `cluster_<seed>.html` to
  `config.GRAPHS_DIR` and returns a `/graphs/<file>` URL. That file is written to the function's
  *ephemeral* FS and is gone by the time the browser GETs it → **the chat link 404s**. The
  engine can't be changed to fix this (frozen). v1 ships with this as a known limitation; the
  dashboard tile is the canonical view. *(Optional v2: a regenerate-on-demand
  `/graphs/{name}` function that re-runs `render_cluster_html` from the seed — blocked on the
  filename slug being lossy for full Solana addresses, so non-trivial.)*

## 4. DECISION: the `api/` naming collision (needs RECTOR's call)

Vercel treats **every** `api/*.py` as a serverless function. The FastAPI app currently lives in
the `api/` package (`api/main.py`, `api/deps.py`, `api/cards.py`, `api/routes/`, …) — so Vercel
would build ~6 stray functions (most handler-less → build errors / 404s), each up to ~175 MB.
That's potentially fatal, not just messy.

Two options:

- **(a) Keep `api/` + try to scope via `vercel.json` `functions`** — least invasive, but
  relies on Vercel suppressing auto-detected functions, which is uncertain. Risk of a failed or
  bloated first deploy.
- **(b) Rename the FastAPI package `api/` → `app/`** (so `app/main.py`, `app/routes/`, …),
  leaving `api/` containing **only** the thin Vercel entry (`api/index.py` → `from app.main
  import app`). This **definitively** eliminates the collision. Cost: a mechanical rename
  touching the `Dockerfile` (`api.main:app` → `app.main:app`), `docker-compose.yml`, the test
  imports (`from api...` → `from app...`), the README quickstart, and this runbook — ~15–25
  edits, all test-verifiable. The ECS/uvicorn path and the frozen engine are untouched.

**Recommendation: (b).** It's the robust fix and unblocks a clean first deploy. (a) is a gamble
that costs a deploy iteration if it fails. RECTOR to confirm before I execute the rename.

## 5. Deploy steps (after §0 gates + §4 decision)

1. Set the three env vars on the Vercel project (dashboard or `vercel env`).
2. `vercel link` (scope `rz1989s`) → `vercel deploy` (preview first, NOT prod).
3. Confirm the build: slim install ≤ 250 MB, SPA built, function packaged.
4. Smoke (see §6): `/api/health` → 200; `/api/assess/{GYaS-mint}` → HIGH; the chat SSE stream.
5. Seed Atlas memory (§0.2) if not done, so the GYaS HIGH-from-memory demo reproduces.
6. On green: `vercel --prod`, then optionally link the URL on Devpost.

## 6. Empirical unknowns (close on first deploy) + fallbacks

### 6.1 SSE streaming on Vercel Python (top risk)
The chat uses `sse-starlette` `EventSourceResponse`. Vercel's Python runtime streaming support
is less battle-tested than Node/Edge. **If SSE doesn't stream**: the chat hangs. Fallback = a
non-streaming `/api/chat` JSON variant (full reply in one blob) — but note the ~45 s turn then
sends no bytes until completion, risking an idle-timeout kill; streaming is genuinely the better
fit. Verify empirically first; keep SSE if it works.

### 6.2 MCP stdio-child in the function env
Each cold function spawns the forensic MCP child (`sys.executable mcp/solana_forensics_mcp.py`)
and keeps it for the chat turn. Lambda-like envs allow `subprocess`, but cold-start (import
qwen-agent + spawn child + first LLM call) adds ~5–15 s — within the 60 s budget. Verify the
child connects + the Helius key (passed via the env allowlist, not inheritance) reaches it.

### 6.3 `buildCommand` behavior
The combined install (`pip install -r requirements-vercel.txt && pip install --no-deps .`) +
SPA build (`cd frontend && npm ci && npm run build`) is wired into `vercel.json buildCommand`.
Confirm Vercel runs it as the single build (it should override default framework detection).

## 7. Known limitations (v1)

- Agent chat `/graphs/*.html` link 404s (§3). Dashboard tile works.
- Cold-start latency on the first request after idle (~5–15 s), then warm.
- Vercel Pro cost ($20/mo) + Atlas (free tier) — ongoing.
- Judging note: the demo is **already submitted** (video + Alibaba proof + blog). A live URL is
  additive, not required. Only link it on Devpost if the smoke (§5.4) is fully green — a
  half-broken live demo is a liability.
