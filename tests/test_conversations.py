from tests.utils import auth_header, register_payload

BASE = "/api/v1/conversations"


async def _two_users(client):
    first = (await client.post("/api/v1/auth/register", json=register_payload())).json()
    second = (await client.post("/api/v1/auth/register", json=register_payload())).json()
    return first, second


async def test_create_dm_returns_both_members(client):
    first, second = await _two_users(client)
    resp = await client.post(
        f"{BASE}/dm", json={"user_id": second["user_id"]}, headers=auth_header(first)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "dm"
    assert len(body["members"]) == 2


async def test_dm_is_idempotent(client):
    first, second = await _two_users(client)
    headers = auth_header(first)
    one = await client.post(f"{BASE}/dm", json={"user_id": second["user_id"]}, headers=headers)
    two = await client.post(f"{BASE}/dm", json={"user_id": second["user_id"]}, headers=headers)
    assert one.json()["id"] == two.json()["id"]


async def test_dm_reversed_creators_share_conversation(client):
    first, second = await _two_users(client)
    one = await client.post(
        f"{BASE}/dm", json={"user_id": second["user_id"]}, headers=auth_header(first)
    )
    two = await client.post(
        f"{BASE}/dm", json={"user_id": first["user_id"]}, headers=auth_header(second)
    )
    assert one.json()["id"] == two.json()["id"]


async def test_cannot_dm_yourself(client):
    first, _ = await _two_users(client)
    resp = await client.post(f"{BASE}/dm", json={"user_id": first["user_id"]}, headers=auth_header(first))
    assert resp.status_code == 400


async def test_dm_with_unknown_user(client):
    first, _ = await _two_users(client)
    resp = await client.post(
        f"{BASE}/dm",
        json={"user_id": "00000000-0000-0000-0000-000000000000"},
        headers=auth_header(first),
    )
    assert resp.status_code == 404


async def test_create_group_with_members(client):
    first, second = await _two_users(client)
    third = (await client.post("/api/v1/auth/register", json=register_payload())).json()
    resp = await client.post(
        f"{BASE}/group",
        json={"name": "Team", "member_ids": [second["user_id"], third["user_id"]]},
        headers=auth_header(first),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["type"] == "group"
    assert body["name"] == "Team"
    assert len(body["members"]) == 3
    creator = next(m for m in body["members"] if m["user"]["id"] == first["user_id"])
    assert creator["role"] == "admin"


async def test_non_member_cannot_access_conversation(client):
    first, second = await _two_users(client)
    outsider = (await client.post("/api/v1/auth/register", json=register_payload())).json()
    dm = await client.post(f"{BASE}/dm", json={"user_id": second["user_id"]}, headers=auth_header(first))
    resp = await client.get(f"{BASE}/{dm.json()['id']}", headers=auth_header(outsider))
    assert resp.status_code == 403


async def test_only_admin_adds_members(client):
    first, second = await _two_users(client)
    third = (await client.post("/api/v1/auth/register", json=register_payload())).json()
    group = await client.post(
        f"{BASE}/group",
        json={"name": "Team", "member_ids": [second["user_id"]]},
        headers=auth_header(first),
    )
    group_id = group.json()["id"]
    resp = await client.post(
        f"{BASE}/{group_id}/members",
        json={"user_ids": [third["user_id"]]},
        headers=auth_header(second),
    )
    assert resp.status_code == 403
    ok = await client.post(
        f"{BASE}/{group_id}/members",
        json={"user_ids": [third["user_id"]]},
        headers=auth_header(first),
    )
    assert ok.status_code == 200
    assert len(ok.json()["members"]) == 3


async def test_remove_member_and_leave(client):
    first, second = await _two_users(client)
    group = await client.post(
        f"{BASE}/group",
        json={"name": "Team", "member_ids": [second["user_id"]]},
        headers=auth_header(first),
    )
    group_id = group.json()["id"]
    removed = await client.delete(
        f"{BASE}/{group_id}/members/{second['user_id']}", headers=auth_header(first)
    )
    assert removed.status_code == 204
    left = await client.post(f"{BASE}/{group_id}/leave", headers=auth_header(first))
    assert left.status_code == 204
    gone = await client.get(f"{BASE}/{group_id}", headers=auth_header(first))
    assert gone.status_code == 403


async def test_list_conversations_unread_and_last_message(client):
    from tests.utils import PASSWORD

    first, second = await _two_users(client)
    dm = await client.post(f"{BASE}/dm", json={"user_id": second["user_id"]}, headers=auth_header(first))
    dm_id = dm.json()["id"]

    for i in range(3):
        sent = await client.post(
            f"/api/v1/conversations/{dm_id}/messages",
            json={"content": f"hello {i}"},
            headers=auth_header(first),
        )
        assert sent.status_code == 201

    listed = await client.get(BASE, headers=auth_header(second))
    assert listed.status_code == 200
    convo = next(c for c in listed.json() if c["id"] == dm_id)
    assert convo["unread_count"] == 3
    assert convo["last_message"]["content"] == "hello 2"

    last_id = convo["last_message"]["id"]
    read = await client.post(f"{BASE}/{dm_id}/read", json={"message_id": last_id}, headers=auth_header(second))
    assert read.status_code == 200

    relisted = await client.get(BASE, headers=auth_header(second))
    convo = next(c for c in relisted.json() if c["id"] == dm_id)
    assert convo["unread_count"] == 0
