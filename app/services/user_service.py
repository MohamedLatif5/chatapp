from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.models import User


async def get_by_identifier(db: AsyncSession, identifier: str) -> User | None:
    stmt = select(User).where(or_(User.username == identifier, User.email == identifier))
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_by_username(db: AsyncSession, username: str) -> User | None:
    return await db.scalar(select(User).where(User.username == username))


async def get_by_email(db: AsyncSession, email: str) -> User | None:
    return await db.scalar(select(User).where(User.email == email))


async def create_user(
    db: AsyncSession,
    username: str,
    email: str,
    password_hash: str,
    full_name: str | None = None,
) -> User:
    if await get_by_username(db, username):
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already taken")
    if await get_by_email(db, email):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = User(username=username, email=email, hashed_password=password_hash, full_name=full_name)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
