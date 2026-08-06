from markrounding import auth


def test_login_wrong_password(client):
    resp = client.post("/api/auth/login", json={"password": "fel"})
    assert resp.status_code == 401


def test_admin_requires_token(client):
    assert client.get("/api/admin/regattas").status_code == 401
    resp = client.get(
        "/api/admin/regattas", headers={"Authorization": "Bearer nonsense"}
    )
    assert resp.status_code == 401


def test_login_rate_limit(client):
    for _ in range(auth.LOGIN_MAX_ATTEMPTS):
        client.post("/api/auth/login", json={"password": "fel"})
    resp = client.post("/api/auth/login", json={"password": "admin"})
    assert resp.status_code == 429


def test_password_roundtrip():
    stored = auth.hash_password("hemligt")
    assert auth.verify_password("hemligt", stored)
    assert not auth.verify_password("fel", stored)
    assert not auth.verify_password("hemligt", "garbage")
