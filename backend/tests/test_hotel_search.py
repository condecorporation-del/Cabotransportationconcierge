import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Company, Hotel, Zone
from app.services.catalog import search_hotels
from scripts.seed_catalog import CATALOG_PATH, seed

CATALOG = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


@pytest.fixture
async def seeded(db: AsyncSession) -> AsyncSession:
    await seed(db, CATALOG)
    return db


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("riu pal", "Riu Palace Cabo San Lucas"),
        ("Zadún", "Zadun, a Ritz Carlton Reserve"),
        ("one only", "One and Only Palmilla"),
        ("golf & spa", "Dreams Los Cabos Suites Golf Resort and Spa"),
        ("BREATHLESS", "Breathless Cabo San Lucas Resort and Spa"),
    ],
)
async def test_finds_hotels_ignoring_accents_case_and_aliases(
    seeded: AsyncSession, query: str, expected: str
) -> None:
    names = [match.name for match in await search_hotels(seeded, query)]
    assert expected in names[:5], names


async def test_returns_zone_in_both_languages(seeded: AsyncSession) -> None:
    [first, *_] = await search_hotels(seeded, "marina fiesta")
    assert first.name == "Marina Fiesta Resort and Spa"
    assert first.zone == "cabo-san-lucas"
    assert set(first.zone_name) == {"en", "es"}


async def test_never_returns_hotels_of_another_company(seeded: AsyncSession) -> None:
    own = seeded.info["company_id"]
    other = Company(name="Other", slug="other")
    seeded.add(other)
    await seeded.flush()
    seeded.info["company_id"] = other.id
    zone = Zone(slug="z", name={"en": "Z"}, drive_minutes_min=1, drive_minutes_max=2)
    seeded.add(zone)
    await seeded.flush()
    seeded.add(Hotel(slug="riu-palace-other", name="Riu Palace Other", zone_id=zone.id))
    await seeded.flush()
    seeded.info["company_id"] = own
    names = [match.name for match in await search_hotels(seeded, "riu palace")]
    assert names
    assert "Riu Palace Other" not in names


async def test_short_or_symbol_queries_are_safe(seeded: AsyncSession) -> None:
    assert await search_hotels(seeded, "r") == []
    assert await search_hotels(seeded, "%%") == []
    assert len(await search_hotels(seeded, "los cabos", limit=10)) == 10
