import uuid

import jwt
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.security import decode_token
from app.db import session as db_session
from app.schemas.message import MessageCreate, MessageOut
from app.services import conversation_service, message_service
from app.services.realtime import broker

router = APIRouter()


async def _handle_ws_message(user_id: uuid.UUID, data: dict) -> None:
    conversation_id = data.get("conversation_id")
    content = str(data.get("content", "")).strip()
    if not conversation_id or not content:
        return
    try:
        conversation_uuid = uuid.UUID(str(conversation_id))
    except ValueError:
        return

    async with db_session.SessionLocal() as db:
        message = await message_service.create_message(
            db,
            sender_id=user_id,
            conversation_id=conversation_uuid,
            content=content,
            message_type=str(data.get("type", "text")),
            reply_to_id=data.get("reply_to_id"),
            attachment_url=data.get("attachment_url"),
        )
        recipient_ids = await conversation_service.get_member_ids(db, conversation_uuid)

    event = {
        "type": "message.new",
        "conversation_id": str(conversation_uuid),
        "message": MessageOut.model_validate(message).model_dump(mode="json"),
    }
    await broker.publish_to_conversation(conversation_uuid, event, recipient_ids)


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
            elif event_type == "message":
                await _handle_ws_message(user_id, data)
    except WebSocketDisconnect:
        pass
    finally:
        broker.manager.disconnect(websocket, user_id)
