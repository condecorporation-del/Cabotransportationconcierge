import asyncio
import os

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import engine_from_url
from app.models import Company, VehicleClass, Zone
from app.services.booking_codes import next_booking_code

Catalog = tuple[Company, Zone, VehicleClass]


async def test_codes_are_sequential_and_restart_each_year(
    db: AsyncSession, catalog: Catalog
) -> None:
    company_id = catalog[0].id

    codes = [await next_booking_code(db, company_id, 2026) for _ in range(3)]

    assert codes == ["CTC-2026-000001", "CTC-2026-000002", "CTC-2026-000003"]
    assert await next_booking_code(db, company_id, 2027) == "CTC-2027-000001"


async def test_fifty_concurrent_bookings_never_share_a_code() -> None:
    """Transacciones reales en conexiones separadas, como reservas que llegan al mismo tiempo."""
    engine = engine_from_url(os.environ["DATABASE_URL"])
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        company = Company(name="Concurrencia", slug="concurrency-test")
        session.add(company)
        await session.commit()

    async def reserve() -> str:
        async with sessions() as session:
            code = await next_booking_code(session, company.id, 2026)
            await session.commit()
            return code

    try:
        codes = await asyncio.gather(*(reserve() for _ in range(50)))
        assert sorted(codes) == [f"CTC-2026-{n:06d}" for n in range(1, 51)]
    finally:
        async with sessions() as session:
            await session.execute(delete(Company).where(Company.id == company.id))
            await session.commit()
        await engine.dispose()
