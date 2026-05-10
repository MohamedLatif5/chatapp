import uuid

import jwt
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.security import decode_token
from app.services.realtime import broker

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)) -> None:
    try:
        payload = decode_token(token, "access")
    except jwt.PyJWTError:
        await websocket.close(code=4401)
        return

    user_id = uuid.UUID(payload["sub"])
    await websocket.accept()
    broker.manager.connect(websocket, user_id)
    try:
        while True:
            data = await websocket.receive_json()
            event_type = data.get("type")
            if event_type == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        broker.manager.disconnect(websocket, user_id)
