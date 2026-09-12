import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from dotenv import load_dotenv
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

load_dotenv()
if not os.environ.get("TEST_DATABASE_URL"):
    raise RuntimeError("Define TEST_DATABASE_URL (ver backend/.env.example)")
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

from app.core.config import get_settings  # noqa: E402  (después de fijar el entorno)
from app.main import create_app  # noqa: E402


@asynccontextmanager
async def running(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http,
    ):
        yield http


@pytest.fixture(autouse=True)
def fresh_settings() -> None:
    get_settings.cache_clear()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with running(create_app()) as http:
        yield http
