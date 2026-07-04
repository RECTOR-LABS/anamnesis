"""FastAPI application entrypoint: mounts the API routers, the health check, and the CORS
policy needed for local frontend development (Phase 2's `npm run dev` on Vite's default
port). Prod serves the frontend same-origin via nginx (docs/plans/2026-07-04-ui-revamp.md
Task 22) — nginx never sends a cross-origin `Origin` header for same-origin requests, so
this middleware is simply inert there, not a prod security surface.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from anamnesis.logging_setup import quiet_http_loggers
from api.routes.assess import router as assess_router
from api.routes.chat import router as chat_router
from api.routes.deployer import router as deployer_router
from api.routes.funding import router as funding_router
from api.routes.graph import router as graph_router
from api.routes.price import router as price_router
from api.routes.profile import router as profile_router

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
app.include_router(price_router)
app.include_router(profile_router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
