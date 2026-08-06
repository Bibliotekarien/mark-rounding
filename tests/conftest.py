"""Test env must be set before markrounding.config is imported (it
validates at import time)."""

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MARKROUNDING_ENV", "development")

from markrounding import auth  # noqa: E402
from markrounding.api.app import create_app  # noqa: E402


@pytest.fixture()
def client(tmp_path):
    auth.reset_rate_limit()
    app = create_app(tmp_path / "test.sqlite")
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def admin_headers(client):
    resp = client.post("/api/auth/login", json={"password": "admin"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['token']}"}
