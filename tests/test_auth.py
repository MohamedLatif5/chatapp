from tests.utils import PASSWORD, auth_header, register_payload

BASE = "/api/v1/auth"


async def test_register_and_login_flow(client):
    payload = register_payload()
    resp = await client.post(f"{BASE}/register", json=payload)
    assert resp.status_code == 201
    tokens = resp.json()
    assert tokens["access_token"] and tokens["refresh_token"]
    assert tokens["username"] == payload["username"]

    login = await client.post(
        f"{BASE}/login", data={"username": payload["username"], "password": PASSWORD}
    )
    assert login.status_code == 200
    assert login.json()["access_token"]

    login_by_email = await client.post(
        f"{BASE}/login", data={"username": payload["email"], "password": PASSWORD}
    )
    assert login_by_email.status_code == 200


async def test_register_duplicate_username(client):
    payload = register_payload()
    assert (await client.post(f"{BASE}/register", json=payload)).status_code == 201
    conflict = register_payload()
    conflict["username"] = payload["username"]
    resp = await client.post(f"{BASE}/register", json=conflict)
    assert resp.status_code == 409


async def test_login_wrong_password(client):
    payload = register_payload()
    await client.post(f"{BASE}/register", json=payload)
    resp = await client.post(
        f"{BASE}/login", data={"username": payload["username"], "password": "WrongPass!99"}
    )
    assert resp.status_code == 401


async def test_refresh_rotates_tokens(client):
    payload = register_payload()
    tokens = (await client.post(f"{BASE}/register", json=payload)).json()
    resp = await client.post(f"{BASE}/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 200
    refreshed = resp.json()
    assert refreshed["access_token"] != tokens["access_token"]


async def test_refresh_rejects_access_token(client):
    payload = register_payload()
    tokens = (await client.post(f"{BASE}/register", json=payload)).json()
    resp = await client.post(f"{BASE}/refresh", json={"refresh_token": tokens["access_token"]})
    assert resp.status_code == 401


async def test_me_requires_auth(client):
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 401


async def test_me_returns_profile(client):
    payload = register_payload()
    tokens = (await client.post(f"{BASE}/register", json=payload)).json()
    resp = await client.get("/api/v1/users/me", headers=auth_header(tokens))
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == payload["username"]
    assert body["email"] == payload["email"]
    assert "hashed_password" not in body
