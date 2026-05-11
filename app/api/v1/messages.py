import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_broker, get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.message import MessageCreate, MessageOut, MessagePage, MessageUpdate
from app.services import conversation_service, message_service
from app.services.realtime import RealtimeBroker

router = APIRouter(tags=["messages"])


def _message_event(event_type: str, message: MessageOut) -> dict:
    return {
        "type": event_type,
        "conversation_id": str(message.conversation_id),
        "message": message.model_dump(mode="json"),
    }


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    conversation_id: uuid.UUID,
    payload: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    broker: RealtimeBroker = Depends(get_broker),
) -> MessageOut:
    message = await message_service.create_message(
        db,
        sender_id=current_user.id,
        conversation_id=conversation_id,
        content=payload.content,
        message_type=payload.type,
        reply_to_id=payload.reply_to_id,
        attachment_url=payload.attachment_url,
    )
    out = MessageOut.model_validate(message)
    recipients = await conversation_service.get_member_ids(db, conversation_id)
    await broker.publish_to_conversation(
        conversation_id, _message_event("message.new", out), recipients
    )
    return out


@router.get("/conversations/{conversation_id}/messages", response_model=MessagePage)
async def list_messages(
    conversation_id: uuid.UUID,
    before_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessagePage:
    rows, has_more = await message_service.list_messages(
        db, current_user.id, conversation_id, before_id, limit
    )
    items = [MessageOut.model_validate(m) for m in rows]
    next_before = items[-1].id if has_more and items else None
    return MessagePage(items=items, has_more=has_more, next_before_id=next_before)


@router.patch("/messages/{message_id}", response_model=MessageOut)
async def edit_message(
    message_id: int,
    payload: MessageUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    broker: RealtimeBroker = Depends(get_broker),
) -> MessageOut:
    message = await message_service.edit_message(db, current_user.id, message_id, payload.content)
    out = MessageOut.model_validate(message)
    recipients = await conversation_service.get_member_ids(db, message.conversation_id)
    await broker.publish_to_conversation(
        message.conversation_id, _message_event("message.updated", out), recipients
    )
    return out


@router.delete("/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(
    message_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    broker: RealtimeBroker = Depends(get_broker),
) -> None:
    message = await message_service.get_message_or_404(db, message_id)
    conversation_id = message.conversation_id
    deleted = MessageOut.model_validate(message)
    await message_service.delete_message(db, current_user.id, message_id)
    recipients = await conversation_service.get_member_ids(db, conversation_id)
    await broker.publish_to_conversation(
        conversation_id, _message_event("message.deleted", deleted), recipients
    )
