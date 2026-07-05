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
path traversal. The filename is validated FIRST — before any filesystem call — against a strict
``cluster_*.html`` shape (an ASCII alnum/underscore stem): real base58 seeds always satisfy it, and
the ASCII-only guard is deliberate — it never widens to the Unicode ``str.isalnum`` that
``graph_view._filename``'s slug tolerates, so no homoglyph/RTL name reaches the disk. Only then is
the path resolved and confirmed inside ``GRAPHS_DIR``. Anything else 404s — never 400 (a prober
cannot distinguish "rejected" from "absent") and never 500 (validating before ``resolve()`` keeps a
null byte or other ``ValueError``-triggering input from escaping as an error oracle).
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from anamnesis import config

router = APIRouter()


def _is_safe_graph_name(name: str) -> bool:
    """True only for the basenames a cluster graph takes — ``<stem>.html`` where <stem> is a
    non-empty run of ASCII alphanumerics and underscores. Rejects everything else: dotfiles, other
    extensions, and any separator, ``..``, or null byte that could climb out of — or crash
    ``resolve()`` on — ``GRAPHS_DIR``. Pure and total (never raises), so it is safe to run as the
    first gate, before the filename ever touches the filesystem."""
    if not name.endswith(".html"):
        return False
    stem = name[: -len(".html")]
    return bool(stem) and all((c.isascii() and c.isalnum()) or c == "_" for c in stem)


@router.get("/graphs/{filename}")
def get_graph_html(filename: str) -> FileResponse:
    """Return the rendered cluster HTML ``filename`` from ``GRAPHS_DIR``, or 404. The name is
    whitelisted BEFORE any path is built or resolved, so hostile input (null bytes, separators)
    404s without ever reaching ``Path.resolve`` (which would raise and 500 on a null byte).
    ``config.GRAPHS_DIR`` is read from the module each call so tests can monkeypatch it; the
    deployed value is fixed at import."""
    if not _is_safe_graph_name(filename):
        raise HTTPException(status_code=404)
    graphs_dir = Path(config.GRAPHS_DIR).resolve()
    target = (graphs_dir / filename).resolve()
    # Defense in depth: the whitelist already blocks separators and ``..``, so this only bites a
    # symlink planted INSIDE GRAPHS_DIR that points out — cheap insurance on a file-serving path.
    if not target.is_relative_to(graphs_dir) or not target.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(str(target), media_type="text/html")
