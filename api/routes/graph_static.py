"""GET /graphs/{filename}: serve a rendered cluster-graph HTML file.

Track B dropped the standalone graph static server (the daemon thread app.py ran over
``config.GRAPHS_DIR``); the deploy now runs ``uvicorn api.main:app`` only. The frozen agent's
``cluster_graph`` tool still renders an interactive vis-network page into ``config.GRAPHS_DIR`` and
returns a link built from ``config.GRAPHS_BASE_URL``. Pointing that base at ``/graphs`` (compose
sets ``ANAMNESIS_GRAPHS_BASE_URL=/graphs``) makes the link same-origin —
``/graphs/cluster_<seed>.html`` — which nginx's one-upstream ``location /`` proxies to this route,
so a "show me the cluster graph" chat turn resolves to a real page instead of the dead
``http://localhost:7866`` dev fallback.

Distinct from ``api/routes/graph.py``, which serves the dashboard's ``/api/graph/{deployer}`` JSON.
This route only streams the already-rendered HTML file back, read-only, and is hardened against
path traversal: the filename must match the exact ``cluster_*.html`` shape ``graph_view._filename``
emits (an ASCII alnum/underscore stem), and the resolved path must stay inside ``GRAPHS_DIR``.
Anything else 404s — never 400, so a prober cannot distinguish "rejected" from "absent".
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from anamnesis import config

router = APIRouter()


def _is_safe_graph_name(name: str) -> bool:
    """True only for the basenames ``graph_view._filename`` produces: ``cluster_<slug>.html`` where
    <slug> is ASCII alphanumerics and underscores. Rejects everything else — dotfiles, other
    extensions, and any separator or ``..`` that could climb out of ``GRAPHS_DIR``."""
    if not name.endswith(".html"):
        return False
    stem = name[: -len(".html")]
    return bool(stem) and all((c.isascii() and c.isalnum()) or c == "_" for c in stem)


@router.get("/graphs/{filename}")
def get_graph_html(filename: str) -> FileResponse:
    """Return the rendered cluster HTML ``filename`` from ``GRAPHS_DIR``, or 404. ``GRAPHS_DIR`` is
    read per request (not at import time) so it tracks the deployed env and test monkeypatching."""
    graphs_dir = Path(config.GRAPHS_DIR).resolve()
    target = (graphs_dir / filename).resolve()
    # Whitelist the name, then confirm the resolved path is still inside GRAPHS_DIR (defense in
    # depth: the whitelist already blocks separators, but containment guards any future loosening).
    if (
        not _is_safe_graph_name(filename)
        or not target.is_relative_to(graphs_dir)
        or not target.is_file()
    ):
        raise HTTPException(status_code=404)
    return FileResponse(str(target), media_type="text/html")
