"""Serving the built single-page dashboard from api.main.

Track B ships the React dashboard (not the old Gradio WebUI) from the same container that
serves the API: `uvicorn api.main:app` serves `frontend/dist` at `/` alongside `/api/*`. The
mount is guarded so a checkout with no production build (CI, the backend test suite, a bare
`npm run dev` workflow) still imports the app and answers `/api/*` — the SPA is simply absent.

These tests exercise the two module-level helpers directly against a throwaway FastAPI app so
the behaviour is verified without a real `npm run build`.
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.main import _mount_frontend


def _make_dist(tmp_path: Path) -> Path:
    """A minimal Vite-style build output: index.html shell + a hashed asset + favicon."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        '<!doctype html><title>Anamnesis</title><div id="root"></div>'
    )
    (dist / "assets" / "index-abc123.js").write_text("console.log('spa')")
    (dist / "favicon.svg").write_text("<svg/>")
    return dist


def _app_with_api() -> FastAPI:
    """A stand-in for api.main.app: one registered /api route, nothing else."""
    app = FastAPI()

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    return app


def test_serves_index_html_at_root(tmp_path: Path) -> None:
    app = _app_with_api()
    _mount_frontend(app, _make_dist(tmp_path))
    resp = TestClient(app).get("/")
    assert resp.status_code == 200
    assert 'id="root"' in resp.text
    assert "text/html" in resp.headers["content-type"]


def test_serves_hashed_assets(tmp_path: Path) -> None:
    app = _app_with_api()
    _mount_frontend(app, _make_dist(tmp_path))
    resp = TestClient(app).get("/assets/index-abc123.js")
    assert resp.status_code == 200
    assert "spa" in resp.text


def test_deep_link_falls_back_to_index(tmp_path: Path) -> None:
    # A client-side route with no matching file must resolve to the app shell, not 404.
    app = _app_with_api()
    _mount_frontend(app, _make_dist(tmp_path))
    resp = TestClient(app).get("/some/client/route")
    assert resp.status_code == 200
    assert 'id="root"' in resp.text


def test_api_route_not_shadowed_by_spa(tmp_path: Path) -> None:
    app = _app_with_api()
    _mount_frontend(app, _make_dist(tmp_path))
    resp = TestClient(app).get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_unknown_api_path_404s_and_never_serves_the_shell(tmp_path: Path) -> None:
    # An undefined /api/* path must 404 as an API miss — NOT masquerade as the SPA shell.
    app = _app_with_api()
    _mount_frontend(app, _make_dist(tmp_path))
    resp = TestClient(app).get("/api/does-not-exist")
    assert resp.status_code == 404
    assert 'id="root"' not in resp.text


def test_no_build_present_is_a_noop(tmp_path: Path) -> None:
    # No frontend/dist (CI / backend tests / dev): app imports, /api works, / is just absent.
    app = _app_with_api()
    _mount_frontend(app, tmp_path / "nonexistent-dist")
    client = TestClient(app)
    assert client.get("/api/health").status_code == 200
    assert client.get("/").status_code == 404
