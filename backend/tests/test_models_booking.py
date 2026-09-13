from datetime import date, time

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Booking,
    BookingItem,
    BookingLeg,
    BookingSource,
    BookingStatus,
    BookingType,
    Company,
    Customer,
    ItemType,
    LegType,
    VehicleClass,
    Zone,
)

Catalog = tuple[Company, Zone, VehicleClass]


async def _booking(db: AsyncSession, vehicle: VehicleClass, *, total_cents: int) -> Booking:
    customer = Customer(name="Ana", email="ana@example.com")
    db.add(customer)
    await db.flush()
    return Booking(
        code="CTC-2026-000001",
        status=BookingStatus.PAID,
        source=BookingSource.WEBSITE,
        booking_type=BookingType.TRANSFER,
        customer_id=customer.id,
        subtotal_cents=23800,
        discount_cents=300,
        total_cents=total_cents,
        legs=[
            BookingLeg(
                leg_type=LegType.ARRIVAL,
                service_date=date(2026, 9, 15),
                service_time=time(14, 10),
                flight_number="AA1245",
                origin="SJD",
                destination="Riu Palace",
                pax_adults=2,
                vehicle_class_id=vehicle.id,
            ),
            BookingLeg(
                leg_type=LegType.DEPARTURE,
                service_date=date(2026, 9, 20),
                pickup_time=time(9, 0),
                origin="Riu Palace",
                destination="SJD",
                pax_adults=2,
                vehicle_class_id=vehicle.id,
            ),
        ],
        items=[
            BookingItem(
                item_type=ItemType.TRANSFER,
                description="Suburban round trip",
                unit_price_cents=19800,
                total_cents=19800,
            ),
            BookingItem(
                item_type=ItemType.EXTRA,
                description="Champagne",
                unit_price_cents=4000,
                total_cents=4000,
            ),
            BookingItem(
                item_type=ItemType.DISCOUNT,
                description="September 10%",
                unit_price_cents=-300,
                total_cents=-300,
            ),
        ],
    )


async def test_booking_with_legs_and_items_reloads_complete(
    db: AsyncSession, catalog: Catalog
) -> None:
    db.add(await _booking(db, catalog[2], total_cents=23500))
    await db.flush()
    db.expunge_all()

    loaded = await db.scalar(
        select(Booking).options(selectinload(Booking.legs), selectinload(Booking.items))
    )

    assert loaded is not None
    assert [leg.leg_type for leg in loaded.legs] == [LegType.ARRIVAL, LegType.DEPARTURE]
    assert sum(item.total_cents for item in loaded.items) == loaded.total_cents == 23500


async def test_booking_totals_must_add_up(db: AsyncSession, catalog: Catalog) -> None:
    db.add(await _booking(db, catalog[2], total_cents=99999))
    with pytest.raises(IntegrityError, match="ck_bookings_totals"):
        await db.flush()


async def test_legs_and_items_require_explicit_loading(db: AsyncSession, catalog: Catalog) -> None:
    db.add(await _booking(db, catalog[2], total_cents=23500))
    await db.flush()
    db.expunge_all()

    loaded = await db.scalar(select(Booking))

    assert loaded is not None
    with pytest.raises(InvalidRequestError):
        _ = loaded.legs
