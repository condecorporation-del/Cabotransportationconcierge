import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Company,
    Customer,
    DiscountType,
    Hotel,
    Promotion,
    Rate,
    TripType,
    VehicleClass,
    Zone,
)


@pytest.fixture
async def catalog(db: AsyncSession) -> tuple[Company, Zone, VehicleClass]:
    company = Company(name="CTC", slug="ctc-catalog")
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


def _rate(zone: Zone, vehicle: VehicleClass, cents: int) -> Rate:
    return Rate(
        zone_id=zone.id, vehicle_class_id=vehicle.id, trip_type=TripType.ONE_WAY, price_cents=cents
    )


async def test_one_rate_per_zone_vehicle_and_trip(
    db: AsyncSession, catalog: tuple[Company, Zone, VehicleClass]
) -> None:
    _, zone, suburban = catalog
    db.add_all([_rate(zone, suburban, 11000), _rate(zone, suburban, 12000)])
    with pytest.raises(IntegrityError, match="uq_rates"):
        await db.flush()


async def test_rate_price_cannot_be_negative(
    db: AsyncSession, catalog: tuple[Company, Zone, VehicleClass]
) -> None:
    _, zone, suburban = catalog
    db.add(_rate(zone, suburban, -1))
    with pytest.raises(IntegrityError, match="price_non_negative"):
        await db.flush()


async def test_hotel_slug_unique_per_company(
    db: AsyncSession, catalog: tuple[Company, Zone, VehicleClass]
) -> None:
    _, zone, _ = catalog
    db.add_all(
        [Hotel(zone_id=zone.id, slug="riu-palace", name=name) for name in ("Riu Palace", "RIU")]
    )
    with pytest.raises(IntegrityError, match="uq_hotels"):
        await db.flush()


async def test_promotion_code_unique_ignoring_case_but_codeless_allowed(
    db: AsyncSession, catalog: tuple[Company, Zone, VehicleClass]
) -> None:
    def promo(code: str | None) -> Promotion:
        return Promotion(
            code=code, name={"en": "Promo"}, discount_type=DiscountType.PERCENT, value=10
        )

    db.add_all([promo(None), promo(None), promo("SEPT10")])
    await db.flush()
    db.add(promo("sept10"))
    with pytest.raises(IntegrityError, match="uq_promotions_company_code"):
        await db.flush()


async def test_customer_email_unique_per_company_ignoring_case(
    db: AsyncSession, catalog: tuple[Company, Zone, VehicleClass]
) -> None:
    db.add_all(
        [Customer(name="Ana", email="Ana@Mail.com"), Customer(name="Ana 2", email="ana@mail.com")]
    )
    with pytest.raises(IntegrityError, match="uq_customers_company_email"):
        await db.flush()


async def test_trigram_extension_is_installed(db: AsyncSession) -> None:
    assert await db.scalar(text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")) == 1
