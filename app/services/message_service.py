import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, ConversationMember, Message
from app.services import conversation_service


def _now() -> datetime:
    return datetime.now(UTC)


async def get_message_or_404(db: AsyncSession, message_id: int) -> Message:
    message = await db.get(Message, message_id)
    if message is None or message.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    return message


async def create_message(
    db: AsyncSession,
    sender_id: uuid.UUID,
    conversation_id: uuid.UUID,
    content: str,
    message_type: str = "text",
    reply_to_id: int | None = None,
    attachment_url: str | None = None,
) -> Message:
    await conversation_service.ensure_member(db, conversation_id, sender_id)

    if reply_to_id is not None:
        reply = await db.get(Message, reply_to_id)
        if reply is None or reply.conversation_id != conversation_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid reply target")

    message = Message(
        conversation_id=conversation_id,
        sender_id=sender_id,
        type=message_type,
        content=content,
        reply_to_id=reply_to_id,
        attachment_url=attachment_url,
    )
    db.add(message)
    conversation = await db.get(Conversation, conversation_id)
    if conversation is not None:
        conversation.last_message_at = _now()
    await db.commit()

    stmt = select(Message).where(Message.id == message.id)
    return (await db.execute(stmt)).scalar_one()


async def list_messages(
    db: AsyncSession,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    before_id: int | None,
    limit: int,
) -> tuple[list[Message], bool]:
    await conversation_service.ensure_member(db, conversation_id, user_id)
    stmt = select(Message).where(Message.conversation_id == conversation_id)
    if before_id is not None:
        stmt = stmt.where(Message.id < before_id)
    stmt = stmt.order_by(Message.id.desc()).limit(limit + 1)
    rows = list((await db.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    return rows[:limit], has_more


async def edit_message(db: AsyncSession, user_id: uuid.UUID, message_id: int, content: str) -> Message:
    message = await get_message_or_404(db, message_id)
    if message.sender_id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only edit your own messages")
    message.content = content
    message.is_edited = True
    message.edited_at = _now()
    await db.commit()
    stmt = select(Message).where(Message.id == message.id)
    return (await db.execute(stmt)).scalar_one()


async def delete_message(db: AsyncSession, user_id: uuid.UUID, message_id: int) -> None:
    message = await get_message_or_404(db, message_id)
    if message.sender_id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can only delete your own messages")
    message.is_deleted = True
    message.content = ""
    message.attachment_url = None
    await db.commit()


async def mark_conversation_read(
    db: AsyncSession, user_id: uuid.UUID, conversation_id: uuid.UUID, message_id: int
) -> int:
    member = await conversation_service.ensure_member(db, conversation_id, user_id)
    message = await db.get(Message, message_id)
    if message is None or message.conversation_id != conversation_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid message for this conversation")
    if member.last_read_message_id is None or message_id > member.last_read_message_id:
        member.last_read_message_id = message_id
        await db.commit()
    return member.last_read_message_id


async def search_messages(
    db: AsyncSession,
    user_id: uuid.UUID,
    query: str,
    conversation_id: uuid.UUID | None = None,
    limit: int = 20,
) -> list[Message]:
    stmt = (
        select(Message)
        .join(
            ConversationMember,
            and_(
                ConversationMember.conversation_id == Message.conversation_id,
                ConversationMember.user_id == user_id,
            ),
        )
        .where(Message.is_deleted.is_(False), Message.content.ilike(f"%{query}%"))
    )
    if conversation_id is not None:
        await conversation_service.ensure_member(db, conversation_id, user_id)
        stmt = stmt.where(Message.conversation_id == conversation_id)
    stmt = stmt.order_by(Message.id.desc()).limit(limit)
    return list((await db.execute(stmt)).scalars().all())


async def count_unread(db: AsyncSession, user_id: uuid.UUID, conversation_id: uuid.UUID) -> int:
    stmt = (
        select(func.count())
        .select_from(Message)
        .join(
            ConversationMember,
            and_(
                ConversationMember.conversation_id == Message.conversation_id,
                ConversationMember.user_id == user_id,
            ),
        )
        .where(
            Message.conversation_id == conversation_id,
            Message.id > func.coalesce(ConversationMember.last_read_message_id, 0),
            Message.sender_id != user_id,
            Message.is_deleted.is_(False),
        )
    )
    return (await db.execute(stmt)).scalar_one()
