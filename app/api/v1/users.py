import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_broker, get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.user import UserOut, UserUpdate
from app.services.realtime import RealtimeBroker

router = APIRouter(prefix="/users", tags=["users"])


class PresenceRequest(BaseModel):
    user_ids: list[uuid.UUID] = Field(max_length=200)


class UserPresenceOut(UserOut):
    online: bool


@router.get("", response_model=list[UserOut])
async def search_users(
    q: str = Query(min_length=1, max_length=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[User]:
    pattern = f"%{q}%"
    stmt = (
        select(User)
        .where(
            User.id != current_user.id,
            User.is_active.is_(True),
            or_(User.username.ilike(pattern), User.full_name.ilike(pattern)),
        )
        .limit(20)
    )
    return list((await db.execute(stmt)).scalars().all())


@router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.patch("/me", response_model=UserOut)
async def update_me(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(current_user, field, value)
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.get("/{user_id}", response_model=UserPresenceOut)
async def get_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    broker: RealtimeBroker = Depends(get_broker),
) -> dict:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    out = UserOut.model_validate(user).model_dump(mode="json")
    out["online"] = await broker.is_user_online(user_id)
    return out


@router.post("/presence")
async def get_presence(
    payload: PresenceRequest,
    _: User = Depends(get_current_user),
    broker: RealtimeBroker = Depends(get_broker),
) -> list[dict]:
    online = await broker.filter_online(payload.user_ids)
    return [
        {"user_id": str(uid), "online": uid in online}
        for uid in payload.user_ids
    ]
