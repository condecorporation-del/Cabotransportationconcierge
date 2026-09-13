import pytest
from sqlalchemy import select

from app.db import normalize_url
from app.main import create_app
from app.models import Company


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "postgresql://u:p@pooler.supabase.com:5432/postgres?pgbouncer=true",
            "postgresql+asyncpg://u:p@pooler.supabase.com:5432/postgres",
        ),
        (
            "postgres://u:p@host/db?application_name=api",
            "postgresql+asyncpg://u:p@host/db?application_name=api",
        ),
        ("postgresql+asyncpg://u:p@localhost/ctc", "postgresql+asyncpg://u:p@localhost/ctc"),
    ],
)
def test_normalize_url_forces_asyncpg_and_drops_pgbouncer(raw: str, expected: str) -> None:
    assert normalize_url(raw) == expected


async def test_uncommitted_writes_are_discarded() -> None:
    app = create_app()
    async with app.router.lifespan_context(app):
        async with app.state.sessionmaker() as session:
            session.add(Company(name="Temporal", slug="discard-me"))
            await session.flush()
        async with app.state.sessionmaker() as session:
            assert await session.scalar(select(Company).where(Company.slug == "discard-me")) is None
