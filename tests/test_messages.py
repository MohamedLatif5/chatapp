from tests.utils import auth_header, register_payload

BASE = "/api/v1/conversations"


async def _dm_with_message(client, content="hello world"):
    first = (await client.post("/api/v1/auth/register", json=register_payload())).json()
    second = (await client.post("/api/v1/auth/register", json=register_payload())).json()
    dm = await client.post(
        f"{BASE}/dm", json={"user_id": second["user_id"]}, headers=auth_header(first)
    )
    dm_id = dm.json()["id"]
    message = await client.post(
        f"/api/v1/conversations/{dm_id}/messages",
        json={"content": content},
        headers=auth_header(first),
    )
    assert message.status_code == 201
    return first, second, dm_id, message.json()


async def test_send_to_non_member_forbidden(client):
    first, second, _, _ = await _dm_with_message(client)
    outsider = (await client.post("/api/v1/auth/register", json=register_payload())).json()
    resp = await client.post(
        f"/api/v1/conversations/{second['user_id']}/messages",
        json={"content": "sneak"},
        headers=auth_header(outsider),
    )
    assert resp.status_code in (403, 404)


async def test_list_messages_pagination(client):
    first, second, dm_id, _ = await _dm_with_message(client, "first")
    headers = auth_header(second)
    for i in range(4):
        await client.post(
            f"/api/v1/conversations/{dm_id}/messages",
            json={"content": f"msg {i}"},
            headers=auth_header(first),
        )

    page1 = await client.get(
        f"/api/v1/conversations/{dm_id}/messages", params={"limit": 2}, headers=headers
    )
    body = page1.json()
    assert body["has_more"] is True
    assert len(body["items"]) == 2
    assert body["items"][0]["content"] == "msg 3"

    page2 = await client.get(
        f"/api/v1/conversations/{dm_id}/messages",
        params={"limit": 2, "before_id": body["next_before_id"]},
        headers=headers,
    )
    body2 = page2.json()
    assert body2["has_more"] is True
    assert body2["items"][0]["content"] == "msg 1"

    page3 = await client.get(
        f"/api/v1/conversations/{dm_id}/messages",
        params={"limit": 2, "before_id": body2["next_before_id"]},
        headers=headers,
    )
    body3 = page3.json()
    assert body3["has_more"] is False
    assert body3["items"][-1]["content"] == "first"


async def test_edit_own_message_only(client):
    first, second, dm_id, message = await _dm_with_message(client)
    edited = await client.patch(
        f"/api/v1/messages/{message['id']}",
        json={"content": "edited!"},
        headers=auth_header(first),
    )
    assert edited.status_code == 200
    assert edited.json()["is_edited"] is True
    assert edited.json()["content"] == "edited!"

    forbidden = await client.patch(
        f"/api/v1/messages/{message['id']}",
        json={"content": "hijack"},
        headers=auth_header(second),
    )
    assert forbidden.status_code == 403


async def test_delete_is_soft(client):
    first, second, dm_id, message = await _dm_with_message(client)
    resp = await client.delete(
        f"/api/v1/messages/{message['id']}", headers=auth_header(first)
    )
    assert resp.status_code == 204

    listed = await client.get(f"/api/v1/conversations/{dm_id}/messages", headers=auth_header(second))
    target = next(m for m in listed.json()["items"] if m["id"] == message["id"])
    assert target["is_deleted"] is True
    assert target["content"] == ""

    edit_gone = await client.patch(
        f"/api/v1/messages/{message['id']}", json={"content": "x"}, headers=auth_header(first)
    )
    assert edit_gone.status_code == 404


async def test_reply_to_message(client):
    first, second, dm_id, message = await _dm_with_message(client)
    resp = await client.post(
        f"/api/v1/conversations/{dm_id}/messages",
        json={"content": "a reply", "reply_to_id": message["id"]},
        headers=auth_header(second),
    )
    assert resp.status_code == 201
    assert resp.json()["reply_to_id"] == message["id"]


async def test_invalid_reply_target_rejected(client):
    first, second, dm_id, _ = await _dm_with_message(client)
    resp = await client.post(
        f"/api/v1/conversations/{dm_id}/messages",
        json={"content": "bad reply", "reply_to_id": 999999},
        headers=auth_header(second),
    )
    assert resp.status_code == 400


async def test_search_messages(client):
    first, second, dm_id, _ = await _dm_with_message(client, "unique needle text")
    await client.post(
        f"/api/v1/conversations/{dm_id}/messages",
        json={"content": "nothing to see"},
        headers=auth_header(first),
    )
    resp = await client.get(
        "/api/v1/search/messages", params={"q": "needle"}, headers=auth_header(second)
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["content"] == "unique needle text"


async def test_search_scoped_to_conversation(client):
    first, second, dm_id, _ = await _dm_with_message(client, "findme alpha")
    other = (await client.post("/api/v1/auth/register", json=register_payload())).json()
    other_dm = await client.post(
        f"{BASE}/dm", json={"user_id": second["user_id"]}, headers=auth_header(other)
    )
    await client.post(
        f"/api/v1/conversations/{other_dm.json()['id']}/messages",
        json={"content": "findme beta"},
        headers=auth_header(other),
    )
    resp = await client.get(
        "/api/v1/search/messages", params={"q": "findme"}, headers=auth_header(first)
    )
    contents = [m["content"] for m in resp.json()["items"]]
    assert contents == ["findme alpha"]
