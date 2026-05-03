"""Login flow and bearer-token gating."""


async def test_login_success(client, admin_password):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": admin_password},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


async def test_login_wrong_password(client):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "wrong"},
    )
    assert resp.status_code == 401


async def test_protected_route_without_bearer_returns_401(client):
    resp = await client.get("/api/v1/bots")
    assert resp.status_code == 401


async def test_protected_route_with_bearer_returns_200(client, auth_headers):
    resp = await client.get("/api/v1/bots", headers=auth_headers)
    assert resp.status_code == 200
