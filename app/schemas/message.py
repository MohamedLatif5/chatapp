import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.user import UserOut


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    type: str = "text"
    reply_to_id: int | None = None
    attachment_url: str | None = Field(default=None, max_length=500)


class MessageUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class MessageReadIn(BaseModel):
    message_id: int


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: uuid.UUID
    sender: UserOut | None
    type: str
    content: str
    attachment_url: str | None
    reply_to_id: int | None
    is_edited: bool
    is_deleted: bool
    edited_at: datetime | None
    created_at: datetime


class MessagePage(BaseModel):
    items: list[MessageOut]
    has_more: bool
    next_before_id: int | None
