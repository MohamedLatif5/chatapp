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


async def _handle_typing(user_id: uuid.UUID, data: dict) -> None:
    conversation_id = data.get("conversation_id")
    if not conversation_id:
        return
    try:
        conversation_uuid = uuid.UUID(str(conversation_id))
    except ValueError:
        return

    async with db_session.SessionLocal() as db:
        member = await conversation_service.get_member(db, conversation_uuid, user_id)
        if member is None:
            return
        recipient_ids = [
            uid for uid in await conversation_service.get_member_ids(db, conversation_uuid)
            if uid != user_id
        ]

    await broker.publish_to_conversation(
        conversation_uuid,
        {
            "type": "typing",
            "conversation_id": str(conversation_uuid),
            "user_id": str(user_id),
        },
        recipient_ids,
    )


async def _update_last_seen(user_id: uuid.UUID) -> None:
    from datetime import UTC, datetime

    from app.models import User

    async with db_session.SessionLocal() as db:
        user = await db.get(User, user_id)
        if user is not None:
            user.last_seen_at = datetime.now(UTC)
            await db.commit()


async def _broadcast_presence(user_id: uuid.UUID, online: bool) -> None:
    async with db_session.SessionLocal() as db:
        recipient_ids = await conversation_service.get_contact_ids(db, user_id)
    await broker.publish_presence(
        {"type": "user.online" if online else "user.offline", "user_id": str(user_id)},
        recipient_ids,
    )


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
    await broker.set_user_online(user_id)
    await _broadcast_presence(user_id, True)
    try:
        while True:
            data = await websocket.receive_json()
            event_type = data.get("type")
            if event_type == "ping":
                await broker.refresh_user_presence(user_id)
                await websocket.send_json({"type": "pong"})
            elif event_type == "message":
                await _handle_ws_message(user_id, data)
            elif event_type == "typing":
                await _handle_typing(user_id, data)
    except WebSocketDisconnect:
        pass
    finally:
        broker.manager.disconnect(websocket, user_id)
        if await broker.set_user_offline(user_id):
            await _update_last_seen(user_id)
            await _broadcast_presence(user_id, False)
