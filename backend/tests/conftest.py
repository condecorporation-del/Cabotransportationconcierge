import json
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
from app.db import engine_from_url, get_session  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Company, VehicleClass, Zone  # noqa: E402
from scripts.seed_catalog import CATALOG_PATH, seed  # noqa: E402


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


@pytest.fixture
async def api(db: AsyncSession) -> AsyncIterator[AsyncClient]:
    """API real sobre la sesión del test (se revierte) con el catálogo real sembrado."""
    await seed(db, json.loads(CATALOG_PATH.read_text(encoding="utf-8")))
    app = create_app()

    async def same_session() -> AsyncIterator[AsyncSession]:
        yield db

    app.dependency_overrides[get_session] = same_session
    async with running(app) as http:
        yield http


@pytest.fixture
async def catalog(db: AsyncSession) -> tuple[Company, Zone, VehicleClass]:
    """Empresa activa en la sesión con una zona y una Suburban."""
    company = Company(name="CTC", slug="ctc-test")
    db.add(company)
    await db.flush()
    db.info["company_id"] = company.id
    zone = Zone(
        slug="cabo-san-lucas",
        name={"en": "Cabo San Lucas"},
        drive_minutes_min=40,
        drive_minutes_max=50,
    )
    suburban = VehicleClass(code="SUBURBAN", name="Chevrolet Suburban", max_pax=5, max_bags=5)
    db.add_all([zone, suburban])
    await db.flush()
    return company, zone, suburban
