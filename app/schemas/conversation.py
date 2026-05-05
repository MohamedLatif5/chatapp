import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.message import MessageOut
from app.schemas.user import UserOut


class DMCreate(BaseModel):
    user_id: uuid.UUID


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    member_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)


class MembersAdd(BaseModel):
    user_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)


class GroupUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ConversationMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user: UserOut
    role: str
    last_read_message_id: int | None
    joined_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: str
    name: str | None
    avatar_url: str | None
    created_by_id: uuid.UUID
    created_at: datetime
    last_message_at: datetime | None
    members: list[ConversationMemberOut]
    last_message: MessageOut | None = None
    unread_count: int = 0
