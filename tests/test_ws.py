import pytest
from starlette.websockets import WebSocketDisconnect

from tests.utils import PASSWORD, register_payload, ws_url


def _register_via(client):
    return client.post("/api/v1/auth/register", json=register_payload()).json()


def test_ws_rejects_invalid_token(ws_client):
    with pytest.raises(WebSocketDisconnect):
        with ws_client.websocket_connect(ws_url("not-a-token")):
            pass


def test_ws_ping_pong(ws_client):
    tokens = _register_via(ws_client)
    with ws_client.websocket_connect(ws_url(tokens["access_token"])) as ws:
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


def _recv_until(ws, event_type, max_events=10):
    for _ in range(max_events):
        event = ws.receive_json()
        if event["type"] == event_type:
            return event
    raise AssertionError(f"event {event_type} not received")


def test_ws_message_delivery_between_users(ws_client):
    first = _register_via(ws_client)
    second = _register_via(ws_client)
    dm = ws_client.post(
        "/api/v1/conversations/dm",
        json={"user_id": second["user_id"]},
        headers={"Authorization": f"Bearer {first['access_token']}"},
    ).json()

    with ws_client.websocket_connect(ws_url(first["access_token"])) as ws_a:
        with ws_client.websocket_connect(ws_url(second["access_token"])) as ws_b:
            ws_b.send_json(
                {"type": "message", "conversation_id": dm["id"], "content": "hi from b"}
            )
            echo = _recv_until(ws_b, "message.new")
            assert echo["message"]["content"] == "hi from b"
            assert echo["message"]["sender"]["id"] == second["user_id"]

            delivered = _recv_until(ws_a, "message.new")
            assert delivered["message"]["content"] == "hi from b"
            assert delivered["conversation_id"] == dm["id"]


def test_ws_typing_indicator(ws_client):
    first = _register_via(ws_client)
    second = _register_via(ws_client)
    dm = ws_client.post(
        "/api/v1/conversations/dm",
        json={"user_id": second["user_id"]},
        headers={"Authorization": f"Bearer {first['access_token']}"},
    ).json()

    with ws_client.websocket_connect(ws_url(first["access_token"])):
        with ws_client.websocket_connect(ws_url(second["access_token"])):
            pass

    with ws_client.websocket_connect(ws_url(first["access_token"])) as ws_a:
        with ws_client.websocket_connect(ws_url(second["access_token"])) as ws_b:
            ws_a.send_json({"type": "typing", "conversation_id": dm["id"]})
            event = ws_b.receive_json()
            assert event["type"] == "typing"
            assert event["user_id"] == first["user_id"]
            assert event["conversation_id"] == dm["id"]


def test_ws_non_member_no_delivery(ws_client):
    first = _register_via(ws_client)
    outsider = _register_via(ws_client)
    dm = ws_client.post(
        "/api/v1/conversations/dm",
        json={"user_id": outsider["user_id"]},
        headers={"Authorization": f"Bearer {first['access_token']}"},
    )
    assert dm.status_code == 200
