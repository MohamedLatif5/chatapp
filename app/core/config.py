from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    PROJECT_NAME: str = "ChatApp API"
    VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"

    SECRET_KEY: str = "dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14

    DATABASE_URL: str = "postgresql+asyncpg://chatapp:chatapp@localhost:5432/chatapp"
    TEST_DATABASE_URL: str = "postgresql+asyncpg://chatapp:chatapp@localhost:5432/chatapp_test"

    REDIS_URL: str = "redis://localhost:6379/0"

    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_MB: int = 10
    ALLOWED_UPLOAD_EXTENSIONS: str = "png,jpg,jpeg,gif,webp,pdf,txt,zip,mp3,mp4"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
