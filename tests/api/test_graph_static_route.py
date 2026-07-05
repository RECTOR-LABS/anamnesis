"""GET /graphs/{filename}: serving rendered cluster-graph HTML (G14).

Track B dropped the standalone graph static server (app.py's daemon thread over GRAPHS_DIR); the
deploy now runs ``uvicorn api.main:app`` only. The agent's ``cluster_graph`` tool still renders an
interactive HTML file into ``config.GRAPHS_DIR`` and links to ``config.GRAPHS_BASE_URL/<file>``.
Setting ``ANAMNESIS_GRAPHS_BASE_URL=/graphs`` makes that link same-origin
(``/graphs/cluster_<seed>.html``), which nginx's one-upstream ``location /`` proxies here — so a
judge who asks chat to "show the cluster graph" gets a working page instead of the dead
``http://localhost:7866`` fallback. The route is read-only and hardened against path traversal.
"""
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from anamnesis import config
from api.main import _mount_frontend, app
from api.routes.graph_static import _is_safe_graph_name
from api.routes.graph_static import router as graph_static_router


@pytest.fixture
def graphs_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point config.GRAPHS_DIR at a throwaway dir (the route resolves it per request)."""
    d = tmp_path / "graphs"
    d.mkdir()
    monkeypatch.setattr(config, "GRAPHS_DIR", str(d))
    return d


def _graphs_only_app() -> FastAPI:
    """The graph-static router in isolation, so a miss is a clean 404 (no SPA catch-all)."""
    a = FastAPI()
    a.include_router(graph_static_router)
    return a


def test_serves_existing_graph_html(graphs_dir: Path) -> None:
    (graphs_dir / "cluster_ABC123.html").write_text("<html>vis-network cluster</html>")
    resp = TestClient(_graphs_only_app()).get("/graphs/cluster_ABC123.html")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "vis-network cluster" in resp.text


def test_missing_graph_404s(graphs_dir: Path) -> None:
    resp = TestClient(_graphs_only_app()).get("/graphs/cluster_does_not_exist.html")
    assert resp.status_code == 404


def test_non_html_name_is_refused(graphs_dir: Path) -> None:
    # A non-.html sibling in the same dir must not be readable through the route.
    (graphs_dir / "secrets.txt").write_text("SECRET")
    resp = TestClient(_graphs_only_app()).get("/graphs/secrets.txt")
    assert resp.status_code == 404
    assert "SECRET" not in resp.text


def test_encoded_traversal_cannot_escape_graphs_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A file OUTSIDE GRAPHS_DIR must never be reachable, however the path is encoded.
    (tmp_path / "outside.html").write_text("TOP-SECRET")
    graphs = tmp_path / "graphs"
    graphs.mkdir()
    monkeypatch.setattr(config, "GRAPHS_DIR", str(graphs))
    client = TestClient(_graphs_only_app())
    for probe in ("..%2foutside.html", "%2e%2e%2foutside.html", "..%2f..%2f..%2fetc%2fpasswd"):
        resp = client.get(f"/graphs/{probe}")
        assert resp.status_code == 404, probe
        assert "TOP-SECRET" not in resp.text


def test_route_registered_in_main_app(graphs_dir: Path) -> None:
    # Prove the router is wired into the real application (not just a throwaway).
    (graphs_dir / "cluster_MAIN.html").write_text("<html>from main app</html>")
    resp = TestClient(app).get("/graphs/cluster_MAIN.html")
    assert resp.status_code == 200
    assert "from main app" in resp.text


def test_route_wins_over_spa_catch_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # In prod the SPA is mounted at / as a catch-all; /graphs/*.html must hit THIS route
    # (registered first), not fall back to the SPA index.html shell.
    graphs = tmp_path / "graphs"
    graphs.mkdir()
    (graphs / "cluster_XYZ.html").write_text("<html>REAL GRAPH</html>")
    monkeypatch.setattr(config, "GRAPHS_DIR", str(graphs))
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text('<!doctype html><div id="root"></div>')
    test_app = FastAPI()
    test_app.include_router(graph_static_router)
    _mount_frontend(test_app, dist)
    resp = TestClient(test_app).get("/graphs/cluster_XYZ.html")
    assert resp.status_code == 200
    assert "REAL GRAPH" in resp.text
    assert 'id="root"' not in resp.text


@pytest.mark.parametrize(
    "name",
    [
        "cluster_ABC.html",
        "cluster_seed123_asof_2024_01_01T00_00_00.html",
        "cluster_So11111111111111111111111.html",
    ],
)
def test_guard_accepts_generated_filenames(name: str) -> None:
    assert _is_safe_graph_name(name)


@pytest.mark.parametrize(
    "name",
    [
        "../../etc/passwd",
        "cluster_x.html/../secret",
        "..",
        ".",
        ".env",
        ".html",
        "",
        "foo.txt",
        "cluster_x.txt",
        "cluster_x.html.txt",
        "cluster x.html",
        "cluster-x.html",
        "cluster_x.HTML",
    ],
)
def test_guard_rejects_unsafe_filenames(name: str) -> None:
    assert not _is_safe_graph_name(name)
