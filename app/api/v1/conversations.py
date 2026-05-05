import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Conversation, ConversationType, User
from app.schemas.conversation import (
    ConversationOut,
    DMCreate,
    GroupCreate,
    GroupUpdate,
    MembersAdd,
)
from app.schemas.message import MessageReadIn
from app.services import conversation_service, message_service

router = APIRouter(prefix="/conversations", tags=["conversations"])


async def get_conversation_or_404(
    conversation_id: uuid.UUID, db: AsyncSession
) -> Conversation:
    conversation = await db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return conversation


@router.post("/dm", response_model=ConversationOut)
async def create_dm(
    payload: DMCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationOut:
    conversation = await conversation_service.get_or_create_dm(db, current_user, payload.user_id)
    return ConversationOut.model_validate(conversation)


@router.post("/group", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
async def create_group(
    payload: GroupCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationOut:
    conversation = await conversation_service.create_group(
        db, current_user, payload.name, payload.member_ids
    )
    return ConversationOut.model_validate(conversation)


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ConversationOut]:
    return [
        ConversationOut.model_validate(item)
        for item in await conversation_service.list_conversations(db, current_user.id)
    ]


@router.get("/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationOut:
    conversation = await get_conversation_or_404(conversation_id, db)
    await conversation_service.ensure_member(db, conversation_id, current_user.id)
    return ConversationOut.model_validate(conversation)


@router.patch("/{conversation_id}", response_model=ConversationOut)
async def update_conversation(
    conversation_id: uuid.UUID,
    payload: GroupUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationOut:
    conversation = await get_conversation_or_404(conversation_id, db)
    if conversation.type != ConversationType.GROUP:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only groups can be renamed")
    await conversation_service.require_admin(db, conversation_id, current_user.id)
    conversation = await conversation_service.rename_conversation(db, conversation, payload.name)
    return ConversationOut.model_validate(conversation)


@router.post("/{conversation_id}/members", response_model=ConversationOut)
async def add_members(
    conversation_id: uuid.UUID,
    payload: MembersAdd,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationOut:
    conversation = await get_conversation_or_404(conversation_id, db)
    await conversation_service.require_admin(db, conversation_id, current_user.id)
    await conversation_service.add_members(db, conversation, payload.user_ids)
    await db.refresh(conversation)
    return ConversationOut.model_validate(conversation)


@router.delete("/{conversation_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    conversation = await get_conversation_or_404(conversation_id, db)
    if conversation.type != ConversationType.GROUP:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Not a group conversation")
    if user_id != current_user.id:
        await conversation_service.require_admin(db, conversation_id, current_user.id)
    await conversation_service.remove_member(db, conversation, user_id)


@router.post("/{conversation_id}/read")
async def mark_read(
    conversation_id: uuid.UUID,
    payload: MessageReadIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str | int]:
    await get_conversation_or_404(conversation_id, db)
    last_read = await message_service.mark_conversation_read(
        db, current_user.id, conversation_id, payload.message_id
    )
    return {
        "conversation_id": str(conversation_id),
        "user_id": str(current_user.id),
        "last_read_message_id": last_read,
    }


@router.post("/{conversation_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    conversation = await get_conversation_or_404(conversation_id, db)
    if conversation.type != ConversationType.GROUP:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot leave a DM")
    await conversation_service.remove_member(db, conversation, current_user.id)
