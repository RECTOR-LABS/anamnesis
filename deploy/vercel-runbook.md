# Vercel deploy runbook — Anamnesis dashboard (serverless)

> Status: **plan + verified feasibility; rename done**. Not yet deployed — blocked on one
> provisioning step (MongoDB, §0.2) and an empirical first-deploy to close the
> platform-specific unknowns (§6). **No Pro tier needed** — Hobby's 300 s covers the ~45 s chat
> (Fluid Compute, default since Apr 2025); the `api/` collision is resolved (renamed to `app/`).
> The dashboard + agent run unchanged; this is a *deployment-target* change, not an engine
> change. The frozen engine (`src/anamnesis/**`, `mcp/**`) is untouched throughout.

## TL;DR — is Vercel viable?

**Yes — verified, not guessed.** The original "don't deploy to Vercel" verdict was based on a
~472 MB dep footprint and an assumed graph-FS blocker. Both turned out to be resolvable:

- **Size**: the bloat is `qwen-agent[gui]` (gradio 187 MB + modelscope 46 MB) which only the
  *legacy* chat WebUI (`app.py`) uses. The dashboard never imports it. Dropping `[gui]` (and
  `uvicorn` — Vercel is the ASGI server) measures **~175 MB** of site-packages, under Vercel's
  250 MB limit. The full serverless import chain (`app.main:app` + `build_agent`) loads cleanly
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

1. **Vercel plan — Hobby is enough for duration.** The chat streams ~45 s; with Fluid Compute
   (enabled by default for new projects since Apr 23, 2025), **Hobby allows 300 s** for Python
   functions — so Pro is **not** required for `maxDuration`. (Pro would raise the cap to 800 s /
   1800 s beta and the bundle size to 500 MB, but neither is needed: ~175 MB deps, ~45 s chat.)
   `vercel.json` sets `maxDuration: 60` as headroom. Only upgrade to Pro if a Hobby limit bites
   (execution-unit quota, cold-start frequency) — none expected for a low-traffic demo.
   - Duration table: https://vercel.com/docs/functions/configuring-functions/duration
   - Fluid Compute default: https://vercel.com/docs/fluid-compute
   - Size + runtimes (Python included): https://vercel.com/docs/functions/limitations
2. **MongoDB** — the ECS self-hosted Mongo is gone. Two paths, both free:
   - **Vercel Marketplace → MongoDB Atlas** (https://vercel.com/marketplace/mongodb-atlas):
     native integration, available on all plans (incl. Hobby), auto-injects the connection URI
     as an env var (exactly the `ANAMNESIS_MONGODB_URI` the engine reads). Verify at "Add"
     whether it offers the **M0 free tier** and whether it bills through Vercel or Atlas (the
     marketplace page is client-rendered, so it couldn't be scraped).
   - **Fallback (always $0):** create an Atlas M0 free cluster (512 MB, plenty) directly on
     mongodb.com, grab the `mongodb+srv://…` URI, paste it as `ANAMNESIS_MONGODB_URI` on the
     Vercel project. Functionally identical — the integration is just a convenience that sets the
     same env var. Allow network access (Vercel egress IPs are dynamic; for a public demo allow
     `0.0.0.0/0`, or use Atlas's Vercel integration / Vercel static IPs).
   Then **re-seed the demo serial-rugger memory** into it:
   `ANAMNESIS_MONGODB_URI=<atlas-uri> PYTHONPATH=src python scripts/seed_demo.py` (idempotent).

## 1. The serverless install (verified + one empirical unknown)

`requirements-vercel.txt` (repo root) is the slim set (qwen-agent with the mcp extra, [gui]
dropped; no uvicorn). Measured **~175 MB** site-packages (python 3.12, fresh venv) — under the
250 MB cap.

The `vercel.json` buildCommand installs the slim deps + anamnesis **editable** + builds the SPA:

```
pip install -r requirements-vercel.txt && pip install -e . --no-deps && cd frontend && npm ci && npm run build
```

`-e . --no-deps` (editable, no deps) is load-bearing and subtle:
- **No `[gui]`:** `--no-deps` skips `pyproject.toml`'s base `dependencies` (`qwen-agent[gui,mcp]`),
  so gradio/modelscope stay out. (A plain `pip install -e .` would drag them back in.)
- **Editable, not copied to site-packages:** the frozen `mcp_entrypoint_path()` resolves the MCP
  child as `Path(__file__).resolve().parents[3] / "mcp" / "solana_forensics_mcp.py"`, which only
  holds when `anamnesis` is imported from `<bundle>/src/anamnesis/agent/agent.py` (parents[3] =
  bundle root, where `mcp/` lives). A NON-editable `pip install . --no-deps` copies anamnesis
  into site-packages -> `__file__` points there -> `parents[3]` is the site-packages parent ->
  the MCP entrypoint path breaks. The **editable** install keeps `__file__` at `src/anamnesis/…`
  AND makes `anamnesis` importable for the spawned MCP child too: the site-packages `.pth`/finder
  it creates is processed at every Python startup, so the fresh child process (which does NOT run
  the `api/index.py` path shim) still gets `src/` on its path.

⚠️ **Key first-deploy unknown (see §6.4):** whether Vercel's function bundling preserves an
editable install's `.pth`/finder with a runtime-valid path to the bundled `src/` (editable
`.pth`s record an absolute build-time path that may not exist in the Lambda extract dir).
`vercel.json` lists `src/**, mcp/**, app/**` in `includeFiles` so the files ARE bundled; only the
path wiring is in question, with a hand-placed `.pth` as the fallback.

*(The repo's `mcp/` dir does not shadow the pip `mcp` SDK: the child runs
`mcp/solana_forensics_mcp.py` with sys.path[0] = the dir containing the script, so `import mcp`
resolves to the SDK in site-packages, not the repo dir.)*

## 2. The architecture

- **SPA** (`frontend/dist`) → served as **Vercel static** (CDN). `outputDirectory: frontend/dist`.
- **API** → **one Python function** that exports the FastAPI ASGI app (`app.main:app`).
  Vercel's runtime detects `app` and serves it; a rewrite routes `/api/*` to it.
  `maxDuration: 60`, `memory: 1024`.
- **Env** (set on the Vercel project): `ANAMNESIS_DASHSCOPE_API_KEY`, `ANAMNESIS_HELIUS_API_KEY`,
  `ANAMNESIS_MONGODB_URI` (the Atlas URI). The MCP child gets the Helius key via its `env`
  block (not inheritance — see `anamnesis.agent.agent.build_function_list`).
- The FastAPI app's SPA mount (`app/main.py::_mount_frontend`) is a guarded no-op serverless
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

## 4. The `api/` naming collision — RESOLVED (rename `api/` → `app/`)

Vercel treats **every** `api/*.py` as a serverless function. With the FastAPI app in the `api/`
package, Vercel would build ~6 stray functions (most handler-less → build errors / 404s), each
up to ~175 MB — potentially fatal. The robust fix (chosen): **rename the FastAPI package `api/`
→ `app/`** (so `app/main.py`, `app/routes/`, …), leaving `api/` free to hold only the thin
Vercel entry (`api/index.py` → `from app.main import app`).

Done in this PR (test-verifiable — 323 backend tests green, ruff clean): `git mv api app` +
`tests/api → tests/app`, the internal `from api…` imports and `api.routes.<mod>.<name>`
monkeypatch strings, the `Dockerfile` (`COPY app` + `uvicorn app.main:app`), the README
quickstart, `deploy/RUNBOOK.md`, and this runbook. The frozen engine (`src/anamnesis/**`,
`mcp/**`) is untouched; the legacy `app.py` WebUI is unaffected (CPython's FileFinder resolves
`import app` to the package; the WebUI test loads `app.py` by file path, not import).

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

### 6.3 `buildCommand` + vercel.json (best-guess, validate on first deploy)
The buildCommand (`pip install -r requirements-vercel.txt && pip install -e . --no-deps && cd
frontend && npm ci && npm run build`) + `outputDirectory: frontend/dist` + the single `api/index.py`
function + the `/api/(.*)` rewrite are wired in `vercel.json`. Confirm Vercel runs the
buildCommand as the single build (overriding default framework detection) and that `api/` now
holds only `index.py` (the rename moved the FastAPI package to `app/`) — so no stray functions.
The `vercel.json` shape (esp. `includeFiles` array + `functions` key) is best-guess from the
docs; expect to iterate it on the first deploy.

### 6.4 Editable-install `.pth` survives bundling? (key unknown)
The editable `pip install -e . --no-deps` writes a site-packages `.pth`/finder pointing at the
build-time `src/` path. In Vercel's Lambda extract, that absolute path may not exist. If the
spawned MCP child can't `import anamnesis` (or `mcp_entrypoint_path()` 404s), drop a hand-placed
`<site-packages>/anamnesis_src.pth` containing the runtime `src/` path (e.g. `/var/task/src`) —
`includeFiles` already bundles `src/**`, so only the path wiring needs fixing.

## 7. Known limitations (v1)

- Agent chat `/graphs/*.html` link 404s (§3). Dashboard tile works.
- Cold-start latency on the first request after idle (~5–15 s), then warm.
- Vercel cost: **$0** (Hobby covers it — 300 s duration, 250 MB size at ~175 MB deps) + Atlas M0 (free). Pro only if a Hobby limit bites.
- Judging note: the demo is **already submitted** (video + Alibaba proof + blog). A live URL is
  additive, not required. Only link it on Devpost if the smoke (§5.4) is fully green — a
  half-broken live demo is a liability.
