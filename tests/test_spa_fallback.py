"""The SPA fallback serves real files from frontend/dist and index.html for
everything else — and never a file outside dist. It used to guard only with
`".." not in path`, so `/%2Fapp/data/markrounding.sqlite` (an absolute path
once %2F is decoded) handed out the whole database, report tokens included."""

import pytest
from fastapi.testclient import TestClient

from markrounding.api import app as app_module


@pytest.fixture()
def spa_client(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("INDEX")
    (dist / "robots.txt").write_text("ROBOTS")
    (tmp_path / "secret.sqlite").write_text("SECRET")
    monkeypatch.setattr(app_module, "FRONTEND_DIST", dist)
    app = app_module.create_app(tmp_path / "test.sqlite")
    with TestClient(app) as c:
        yield c, tmp_path / "secret.sqlite"


def test_serves_files_in_dist_and_index_for_routes(spa_client):
    client, _ = spa_client
    assert client.get("/robots.txt").text == "ROBOTS"
    assert client.get("/regatta/varregattan").text == "INDEX"
    assert client.get("/").text == "INDEX"


def test_never_serves_files_outside_dist(spa_client):
    client, secret = spa_client
    absolute = str(secret).lstrip("/")
    for path in [
        f"/%2F{absolute}",
        f"/%2f{absolute.replace('/', '%2f')}",
        "/%2e%2e/secret.sqlite",
        "/..%2Fsecret.sqlite",
        "/%2Fetc/hostname",
    ]:
        resp = client.get(path)
        assert resp.text == "INDEX", path
