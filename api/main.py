"""FastAPI application entrypoint: mounts the API routers, the health check, and the CORS
policy needed for local frontend development (Phase 2's `npm run dev` on Vite's default
port). Prod serves the frontend same-origin via nginx (docs/plans/2026-07-04-ui-revamp.md
Task 22) — nginx never sends a cross-origin `Origin` header for same-origin requests, so
this middleware is simply inert there, not a prod security surface.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.assess import router as assess_router

app = FastAPI(title="Anamnesis API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(assess_router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
