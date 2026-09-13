import asyncio

from alembic import context
from sqlalchemy.engine import Connection

import app.models  # noqa: F401  (registra las tablas en Base.metadata)
from app.core.config import get_settings
from app.db import Base, engine_from_url


def _migrate(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def _run() -> None:
    settings = get_settings()
    # Migraciones por la conexión Direct, nunca por el pooler (WORKPLAN D2).
    engine = engine_from_url(settings.database_url_direct or settings.database_url, pooled=False)
    async with engine.connect() as connection:
        await connection.run_sync(_migrate)
    await engine.dispose()


asyncio.run(_run())
