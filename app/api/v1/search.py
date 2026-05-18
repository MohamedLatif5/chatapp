import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.message import MessageOut
from app.services import message_service

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/messages")
async def search_messages(
    q: str = Query(min_length=1, max_length=200),
    conversation_id: uuid.UUID | None = None,
    limit: int = Query(default=20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    messages = await message_service.search_messages(
        db, current_user.id, q, conversation_id, limit
    )
    return {"items": [MessageOut.model_validate(m) for m in messages], "query": q}
