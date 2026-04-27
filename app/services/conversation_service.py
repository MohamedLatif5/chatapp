import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, ConversationMember, ConversationType, MemberRole, User


async def get_member(
    db: AsyncSession, conversation_id: uuid.UUID, user_id: uuid.UUID
) -> ConversationMember | None:
    stmt = select(ConversationMember).where(
        ConversationMember.conversation_id == conversation_id,
        ConversationMember.user_id == user_id,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def ensure_member(
    db: AsyncSession, conversation_id: uuid.UUID, user_id: uuid.UUID
) -> ConversationMember:
    member = await get_member(db, conversation_id, user_id)
    if member is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this conversation")
    return member


async def get_member_ids(
    db: AsyncSession, conversation_id: uuid.UUID
) -> list[uuid.UUID]:
    stmt = select(ConversationMember.user_id).where(
        ConversationMember.conversation_id == conversation_id
    )
    return list((await db.execute(stmt)).scalars().all())


async def get_or_create_dm(db: AsyncSession, me: User, other_id: uuid.UUID) -> Conversation:
    if other_id == me.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot create a DM with yourself")
    other = await db.get(User, other_id)
    if other is None or not other.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    stmt = (
        select(Conversation)
        .join(ConversationMember, ConversationMember.conversation_id == Conversation.id)
        .where(Conversation.type == ConversationType.DM)
        .where(ConversationMember.user_id.in_([me.id, other.id]))
        .group_by(Conversation.id)
        .having(func.count(func.distinct(ConversationMember.user_id)) == 2)
    )
    conversation = (await db.execute(stmt)).scalar_one_or_none()
    if conversation is not None:
        return conversation

    conversation = Conversation(type=ConversationType.DM, created_by_id=me.id)
    db.add_all(
        [
            conversation,
            ConversationMember(
                conversation=conversation, user_id=me.id, role=MemberRole.MEMBER.value
            ),
            ConversationMember(
                conversation=conversation, user_id=other.id, role=MemberRole.MEMBER.value
            ),
        ]
    )
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        return (await db.execute(stmt)).scalar_one()
    stmt = select(Conversation).where(Conversation.id == conversation.id)
    return (await db.execute(stmt)).scalar_one()
