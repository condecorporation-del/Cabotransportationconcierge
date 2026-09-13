import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from dotenv import load_dotenv
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

load_dotenv()
if not os.environ.get("TEST_DATABASE_URL"):
    raise RuntimeError("Define TEST_DATABASE_URL (ver backend/.env.example)")
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ.pop("DATABASE_URL_DIRECT", None)

from alembic import command  # noqa: E402  (después de fijar el entorno)
from alembic.config import Config  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db import engine_from_url  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    """Prueba las migraciones de verdad: base vacía → head en cada corrida."""
    config = Config("alembic.ini")
    command.downgrade(config, "base")
    command.upgrade(config, "head")


@pytest.fixture(autouse=True)
def fresh_settings() -> None:
    get_settings.cache_clear()


@asynccontextmanager
async def running(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http,
    ):
        yield http


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with running(create_app()) as http:
        yield http


@pytest.fixture
async def db() -> AsyncIterator[AsyncSession]:
    """Sesión dentro de una transacción que se revierte al terminar cada test."""
    engine = engine_from_url(os.environ["DATABASE_URL"], pooled=False)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        yield session
        await session.close()
        await transaction.rollback()
    await engine.dispose()
