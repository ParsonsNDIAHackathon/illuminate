"""Production SPA file serving must remain inside the built distribution."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from illuminate import main


def test_dist_file_allows_built_assets(tmp_path: Path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    asset = dist / "asset.js"
    asset.write_text("ok")
    assert main._dist_file("asset.js", dist) == asset.resolve()


def test_dist_file_rejects_traversal_and_escaping_symlink(tmp_path: Path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("must not be served")
    (dist / "escape.txt").symlink_to(secret)
    assert main._dist_file("../secret.txt", dist) is None
    assert main._dist_file("escape.txt", dist) is None


def test_frontend_routes_serve_root_asset_and_history_fallback(tmp_path: Path):
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text('<div id="app"></div>')
    (assets / "app.js").write_text("console.log('ok')")
    test_app = FastAPI()
    main._mount_frontend(test_app, dist.resolve())

    client = TestClient(test_app)
    assert client.get("/").text == '<div id="app"></div>'
    assert client.get("/portfolio").text == '<div id="app"></div>'
    assert client.get("/programs").text == '<div id="app"></div>'
    assert client.get("/assets/app.js").text == "console.log('ok')"


def test_main_app_registers_mcp_redirect_and_mount():
    routes = [(getattr(route, "path", None), type(route).__name__) for route in main.app.routes]
    assert ("/mcp", "APIRoute") in routes
    assert ("/mcp", "Mount") in routes

    client = TestClient(main.app, raise_server_exceptions=False)
    redirect = client.post("/mcp", follow_redirects=False)
    assert redirect.status_code == 307
    assert redirect.headers["location"] == "/mcp/"
    assert client.get("/mcp/").status_code == 503