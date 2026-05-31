import asyncio

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.db import session as db_session
from app.db.base import Base
from app.main import app

test_engine = create_async_engine(
    settings.TEST_DATABASE_URL, poolclass=NullPool, pool_pre_ping=True
)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)


async def _override_get_db():
    async with TestSessionLocal() as session:
        yield session


@pytest.fixture(scope="session", autouse=True)
def _database():
    async def setup():
        admin = create_async_engine(
            settings.DATABASE_URL, isolation_level="AUTOCOMMIT", poolclass=NullPool
        )
        async with admin.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = 'chatapp_test'")
            )
            if not exists:
                await conn.execute(text("CREATE DATABASE chatapp_test"))
        await admin.dispose()

        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(setup())
    db_session.SessionLocal = TestSessionLocal
    app.dependency_overrides[db_session.get_db] = _override_get_db
    yield
    app.dependency_overrides.pop(db_session.get_db, None)


@pytest.fixture(autouse=True)
def _clean_tables():
    async def clean():
        tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        async with test_engine.begin() as conn:
            await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))

    asyncio.run(clean())
    yield


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def ws_client():
    with TestClient(app) as c:
        yield c
