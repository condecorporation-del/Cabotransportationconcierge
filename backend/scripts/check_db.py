"""Diagnóstico rápido de la base de datos (WORKPLAN F1.12).

uv run python -m scripts.check_db

Sale con código 1 si no conecta o si faltan migraciones: sirve como verificación en un deploy.
"""

import asyncio
import sys
import time
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import get_settings
from app.db import engine_from_url

TABLES = ("companies", "hotels", "rates", "bookings", "payments", "email_outbox")


def head_revision() -> str | None:
    return ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()


async def check(connection: AsyncConnection, head: str | None) -> dict[str, Any]:
    started = time.perf_counter()
    await connection.execute(text("SELECT 1"))
    latency_ms = round((time.perf_counter() - started) * 1000, 1)

    current = None
    if await connection.scalar(text("SELECT to_regclass('alembic_version')")):
        current = await connection.scalar(text("SELECT version_num FROM alembic_version"))
    rows = {}
    if current == head:
        for table in TABLES:  # nombres fijos del código, nunca entrada del usuario
            rows[table] = await connection.scalar(text(f"SELECT count(*) FROM {table}"))  # noqa: S608

    return {
        "latency_ms": latency_ms,
        "server_version": await connection.scalar(text("SHOW server_version")),
        "migration": current,
        "migration_head": head,
        "up_to_date": current == head,
        "rows": rows,
    }


async def _main() -> int:
    engine = engine_from_url(get_settings().database_url, pooled=False)
    try:
        async with engine.connect() as connection:
            report = await check(connection, head_revision())
    except (OSError, SQLAlchemyError) as error:
        print(f"ERROR: no se pudo conectar a la base de datos ({type(error).__name__})")
        return 1
    finally:
        await engine.dispose()

    for key, value in report.items():
        print(f"{key:>15}: {value}")
    if not report["up_to_date"]:
        print("ERROR: faltan migraciones; corre `uv run alembic upgrade head`")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
