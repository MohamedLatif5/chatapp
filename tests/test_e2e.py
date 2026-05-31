from tests.utils import auth_header, register_payload, ws_url


def _headers(tokens):
    return auth_header(tokens)


def _recv_until(ws, event_type, max_events=15):
    for _ in range(max_events):
        event = ws.receive_json()
        if event["type"] == event_type:
            return event
    raise AssertionError(f"event {event_type} not received")


def test_full_chat_journey(ws_client):
    c = ws_client
    base = "/api/v1"

    alice = c.post(f"{base}/auth/register", json=register_payload()).json()
    bob = c.post(f"{base}/auth/register", json=register_payload()).json()
    assert alice["access_token"] and bob["access_token"]

    me = c.get(f"{base}/users/me", headers=_headers(alice))
    assert me.status_code == 200
    assert me.json()["username"] == alice["username"]

    found = c.get(f"{base}/users", params={"q": bob["username"]}, headers=_headers(alice))
    assert found.status_code == 200
    match = next(u for u in found.json() if u["id"] == bob["user_id"])

    dm = c.post(f"{base}/conversations/dm", json={"user_id": match["id"]}, headers=_headers(alice))
    assert dm.status_code == 200
    dm_id = dm.json()["id"]

    sent = c.post(
        f"{base}/conversations/{dm_id}/messages",
        json={"content": "hello bob"},
        headers=_headers(alice),
    )
    assert sent.status_code == 201
    first_message = sent.json()

    bob_list = c.get(f"{base}/conversations", headers=_headers(bob))
    convo = next(cv for cv in bob_list.json() if cv["id"] == dm_id)
    assert convo["unread_count"] == 1
    assert convo["last_message"]["content"] == "hello bob"

    edited = c.patch(
        f"{base}/messages/{first_message['id']}",
        json={"content": "hello bob (edited)"},
        headers=_headers(alice),
    )
    assert edited.status_code == 200
    assert edited.json()["is_edited"] is True

    search = c.get(f"{base}/search/messages", params={"q": "edited"}, headers=_headers(bob))
    assert any("edited" in m["content"] for m in search.json()["items"])

    upload = c.post(
        f"{base}/uploads",
        files={"file": ("avatar.png", b"\x89PNG\r\n\x1a\nfakepng", "image/png")},
        headers=_headers(alice),
    )
    assert upload.status_code == 200
    assert upload.json()["url"].endswith(".png")

    with c.websocket_connect(ws_url(alice["access_token"])) as ws_alice:
        with c.websocket_connect(ws_url(bob["access_token"])) as ws_bob:
            ws_bob.send_json({"type": "ping"})
            assert _recv_until(ws_bob, "pong") == {"type": "pong"}

            ws_alice.send_json({"type": "typing", "conversation_id": dm_id})
            typing = _recv_until(ws_bob, "typing")
            assert typing["user_id"] == alice["user_id"]

            ws_bob.send_json(
                {"type": "message", "conversation_id": dm_id, "content": "hi alice"}
            )
            received = _recv_until(ws_alice, "message.new")
            assert received["message"]["content"] == "hi alice"
            echo = _recv_until(ws_bob, "message.new")
            assert echo["message"]["content"] == "hi alice"

            presence = c.post(
                f"{base}/users/presence",
                json={"user_ids": [alice["user_id"], bob["user_id"]]},
                headers=_headers(alice),
            )
            statuses = {p["user_id"]: p["online"] for p in presence.json()}
            assert statuses[alice["user_id"]] is True
            assert statuses[bob["user_id"]] is True

            read = c.post(
                f"{base}/conversations/{dm_id}/read",
                json={"message_id": echo["message"]["id"]},
                headers=_headers(alice),
            )
            assert read.status_code == 200
            read_event = _recv_until(ws_bob, "message.read")
            assert read_event["user_id"] == alice["user_id"]

    deleted = c.delete(f"{base}/messages/{first_message['id']}", headers=_headers(alice))
    assert deleted.status_code == 204

    import time

    last_seen = None
    for _ in range(40):
        detail = c.get(f"{base}/users/{bob['user_id']}", headers=_headers(alice))
        assert detail.status_code == 200
        last_seen = detail.json()["last_seen_at"]
        if last_seen is not None:
            break
        time.sleep(0.05)
    assert last_seen is not None
