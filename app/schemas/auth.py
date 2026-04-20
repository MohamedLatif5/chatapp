from pydantic import BaseModel, EmailStr


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthResponse(TokenPair):
    user_id: str
    username: str
    email: EmailStr


class RefreshRequest(BaseModel):
    refresh_token: str
