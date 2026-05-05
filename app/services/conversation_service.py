import uuid

from fastapi import HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, ConversationMember, ConversationType, MemberRole, Message, User


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


async def create_group(
    db: AsyncSession, me: User, name: str, member_ids: list[uuid.UUID]
) -> Conversation:
    unique_ids = {mid for mid in member_ids if mid != me.id}
    existing = list(
        (await db.execute(select(User).where(User.id.in_(unique_ids)))).scalars().all()
    )
    if len(existing) != len(unique_ids):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "One or more users not found")

    conversation = Conversation(
        type=ConversationType.GROUP, name=name, created_by_id=me.id
    )
    db.add(conversation)
    db.flush()
    db.add(
        ConversationMember(
            conversation=conversation, user_id=me.id, role=MemberRole.ADMIN.value
        )
    )
    for member in existing:
        db.add(
            ConversationMember(
                conversation=conversation, user_id=member.id, role=MemberRole.MEMBER.value
            )
        )
    await db.commit()
    return (await db.execute(select(Conversation).where(Conversation.id == conversation.id))).scalar_one()


async def require_admin(
    db: AsyncSession, conversation_id: uuid.UUID, user_id: uuid.UUID
) -> ConversationMember:
    member = await ensure_member(db, conversation_id, user_id)
    if member.role != MemberRole.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin privileges required")
    return member


async def add_members(
    db: AsyncSession, conversation: Conversation, user_ids: list[uuid.UUID]
) -> list[ConversationMember]:
    if conversation.type != ConversationType.GROUP:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Members can only be added to groups")
    existing_ids = {m.user_id for m in conversation.members}
    new_ids = [uid for uid in dict.fromkeys(user_ids) if uid not in existing_ids]
    if not new_ids:
        return []
    found = list(
        (await db.execute(select(User).where(User.id.in_(new_ids)))).scalars().all()
    )
    members = [
        ConversationMember(
            conversation=conversation, user_id=u.id, role=MemberRole.MEMBER.value
        )
        for u in found
    ]
    db.add_all(members)
    await db.commit()
    for m in members:
        await db.refresh(m)
    return members


async def remove_member(
    db: AsyncSession, conversation: Conversation, target_id: uuid.UUID
) -> None:
    member = await get_member(db, conversation.id, target_id)
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    await db.delete(member)
    await db.commit()


async def rename_conversation(
    db: AsyncSession, conversation: Conversation, name: str
) -> Conversation:
    conversation.name = name
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def list_conversations(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    member_convos = (
        select(ConversationMember.conversation_id)
        .where(ConversationMember.user_id == user_id)
        .subquery()
    )
    stmt = (
        select(Conversation)
        .join(member_convos, member_convos.c.conversation_id == Conversation.id)
        .order_by(func.coalesce(Conversation.last_message_at, Conversation.created_at).desc())
    )
    conversations = list((await db.execute(stmt)).scalars().all())

    unread_counts: dict[uuid.UUID, int] = {}
    last_messages: dict[uuid.UUID, Message] = {}
    if conversations:
        unread_stmt = (
            select(Message.conversation_id, func.count().label("unread"))
            .join(
                ConversationMember,
                and_(
                    ConversationMember.conversation_id == Message.conversation_id,
                    ConversationMember.user_id == user_id,
                ),
            )
            .where(
                Message.id > func.coalesce(ConversationMember.last_read_message_id, 0),
                Message.sender_id != user_id,
                Message.is_deleted.is_(False),
            )
            .group_by(Message.conversation_id)
        )
        rows = (await db.execute(unread_stmt)).all()
        unread_counts = {row.conversation_id: row.unread for row in rows}

        max_ids = (
            select(Message.conversation_id, func.max(Message.id).label("max_id"))
            .where(Message.conversation_id.in_([c.id for c in conversations]))
            .group_by(Message.conversation_id)
            .subquery()
        )
        last_stmt = select(Message).join(
            max_ids,
            and_(max_ids.c.conversation_id == Message.conversation_id, max_ids.c.max_id == Message.id),
        )
        last_messages = {m.conversation_id: m for m in (await db.execute(last_stmt)).scalars()}

    return [
        {
            "id": c.id,
            "type": c.type,
            "name": c.name,
            "avatar_url": c.avatar_url,
            "created_by_id": c.created_by_id,
            "created_at": c.created_at,
            "last_message_at": c.last_message_at,
            "members": c.members,
            "last_message": last_messages.get(c.id),
            "unread_count": unread_counts.get(c.id, 0),
        }
        for c in conversations
    ]
