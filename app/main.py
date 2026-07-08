"""FastAPI application entrypoint: mounts the API routers, the health check, and the CORS
policy needed for local frontend development (Phase 2's `npm run dev` on Vite's default
port). Prod serves the frontend same-origin via nginx (docs/plans/2026-07-04-ui-revamp.md
Task 22) — nginx never sends a cross-origin `Origin` header for same-origin requests, so
this middleware is simply inert there, not a prod security surface.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from anamnesis.logging_setup import quiet_http_loggers
from app.routes.assess import router as assess_router
from app.routes.chat import router as chat_router
from app.routes.deployer import router as deployer_router
from app.routes.funding import router as funding_router
from app.routes.graph import router as graph_router
from app.routes.graph_static import router as graph_static_router
from app.routes.price import router as price_router
from app.routes.profile import router as profile_router

app = FastAPI(title="Anamnesis API")

# Raise httpx/httpcore to WARNING before any request can run: the chat route drives the agent
# -> forensic MCP tools -> Helius reads, whose INFO request line carries the Helius api-key in
# the URL. Module level (not a @app.on_event("startup") handler) so this is active
# unconditionally — including under a bare `TestClient(app)`, which never runs ASGI lifespan
# events — and covers the assess route too. logging_setup imports only stdlib `logging`, so
# this stays CI-safe.
quiet_http_loggers()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(assess_router)
app.include_router(chat_router)
app.include_router(deployer_router)
app.include_router(funding_router)
app.include_router(graph_router)
app.include_router(graph_static_router)
app.include_router(price_router)
app.include_router(profile_router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


# ── Frontend (Track B) ────────────────────────────────────────────────────────────────────────
# Serve the built React dashboard (frontend/dist) from this same app, so ONE
# `uvicorn app.main:app` container answers both the SPA at `/` and the API at `/api/*`. The mount
# is guarded on the build's presence: a checkout with no `npm run build` output (CI, the backend
# test suite, a bare Vite dev workflow) imports cleanly and still answers `/api/*` — the SPA is
# simply absent. Mounted LAST, so every `/api/*` route is matched before this catch-all.
class _SPAStaticFiles(StaticFiles):
    """StaticFiles with a client-side-routing fallback: an unknown non-API, non-asset path
    resolves to index.html (the app shell) instead of 404, so browser deep links load the SPA.
    Three path classes are deliberately excluded so they surface real 404s, not the shell:
    `api`/`api/*` (API misses must stay API errors), `assets/*` (hashed build files — a stale
    `assets/index-<oldhash>.js` request from a tab open across a redeploy must 404 so the browser
    errors cleanly, not receive 200 text/html it then fails to parse as JS), and `graphs`/`graphs/*`
    (the cluster-graph route's namespace — a miss there is a dead graph link, not a client route)."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if (exc.status_code == 404
                    and path not in ("api", "graphs")
                    and not path.startswith(("api/", "assets/", "graphs/"))):
                return await super().get_response("index.html", scope)
            raise


def _mount_frontend(application: FastAPI, dist_dir: Path) -> None:
    """Mount the built SPA at `/` when `dist_dir` exists; a no-op otherwise (build-free runs)."""
    if dist_dir.is_dir():
        application.mount("/", _SPAStaticFiles(directory=str(dist_dir), html=True), name="spa")


# frontend/dist sits at the repo root, one level up from api/.
_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
_mount_frontend(app, _FRONTEND_DIST)
