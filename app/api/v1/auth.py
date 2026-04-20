from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, create_refresh_token, hash_password, verify_password
from app.db.session import get_db
from app.models import User
from app.schemas.auth import AuthResponse
from app.schemas.user import UserCreate
from app.services import user_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _build_auth_response(user: User) -> AuthResponse:
    return AuthResponse(
        user_id=str(user.id),
        username=user.username,
        email=user.email,
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)) -> AuthResponse:
    user = await user_service.create_user(
        db,
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
    )
    return _build_auth_response(user)


@router.post("/login", response_model=AuthResponse)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> AuthResponse:
    user = await user_service.get_by_identifier(db, form.username)
    if user is None or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect username or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is disabled")
    return _build_auth_response(user)
