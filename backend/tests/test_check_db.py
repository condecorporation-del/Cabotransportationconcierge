import os

from app.db import engine_from_url
from scripts.check_db import TABLES, check, head_revision


async def test_check_reports_database_at_head() -> None:
    engine = engine_from_url(os.environ["DATABASE_URL"], pooled=False)
    try:
        async with engine.connect() as connection:
            report = await check(connection, head_revision())
    finally:
        await engine.dispose()

    assert report["up_to_date"] is True
    assert report["migration"] == report["migration_head"] is not None
    assert set(report["rows"]) == set(TABLES)
    assert report["latency_ms"] >= 0


async def test_check_detects_pending_migrations() -> None:
    engine = engine_from_url(os.environ["DATABASE_URL"], pooled=False)
    try:
        async with engine.connect() as connection:
            report = await check(connection, "a_future_revision")
    finally:
        await engine.dispose()

    assert report["up_to_date"] is False
    assert report["rows"] == {}
