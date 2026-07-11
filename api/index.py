"""Vercel serverless function entry — re-exports the FastAPI ASGI app for /api/* routing.

Vercel's Python runtime detects the `app` ASGI object and serves it; vercel.json rewrites
/api/* here, while the React SPA is served as Vercel static (frontend/dist) — NOT through this
function.

The `anamnesis` package is imported from the `src/` layout (NOT site-packages) on purpose: the
frozen `anamnesis.agent.agent.mcp_entrypoint_path()` resolves the MCP child as
`Path(__file__).resolve().parents[3] / "mcp" / "solana_forensics_mcp.py"`, which only holds when
`anamnesis` is imported from `<bundle>/src/anamnesis/agent/agent.py` (parents[3] = the bundle
root, where `mcp/` lives). Installing anamnesis into site-packages would make `__file__` point
there instead, breaking that path. So this entry puts `src/` (for `anamnesis`) and the repo
root (for the `app` FastAPI package) on the path.

The spawned MCP CHILD is a fresh `sys.executable` process that does NOT run this shim, so it
needs `src/` on its own path via a site-packages `.pth` (the editable install `pip install -e .
--no-deps` in the buildCommand sets that up) — see deploy/vercel-runbook.md §1 for why this is
the key first-deploy unknown.

This file is Vercel-only — not imported by the ECS/uvicorn deploy (which serves `app.main:app`
directly via the Dockerfile) or by the tests.
"""
import pathlib
import sys

_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))           # the `app` FastAPI package (lives at the repo root)
sys.path.insert(0, str(_ROOT / "src"))   # the `anamnesis` package (src/ layout — see mcp_entrypoint_path)

from app.main import app  # noqa: E402,F401 — the FastAPI ASGI app; Vercel detects `app`