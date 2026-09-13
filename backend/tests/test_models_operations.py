from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Booking,
    BookingAssignment,
    BookingLeg,
    BookingSource,
    BookingStatus,
    BookingType,
    Company,
    Customer,
    Driver,
    LegType,
    Vehicle,
    VehicleClass,
    Zone,
)

Catalog = tuple[Company, Zone, VehicleClass]


@pytest.fixture
async def leg(db: AsyncSession, catalog: Catalog) -> BookingLeg:
    customer = Customer(name="Ana", email="ana@example.com")
    db.add(customer)
    await db.flush()
    arrival = BookingLeg(
        leg_type=LegType.ARRIVAL,
        service_date=date(2026, 9, 15),
        origin="SJD",
        destination="Riu Palace",
        pax_adults=2,
        vehicle_class_id=catalog[2].id,
    )
    db.add(
        Booking(
            code="CTC-2026-000020",
            status=BookingStatus.CONFIRMED,
            source=BookingSource.ADMIN,
            booking_type=BookingType.TRANSFER,
            customer_id=customer.id,
            subtotal_cents=11000,
            total_cents=11000,
            legs=[arrival],
        )
    )
    await db.flush()
    return arrival


def _vehicle(catalog: Catalog, plate: str) -> Vehicle:
    return Vehicle(
        vehicle_class_id=catalog[2].id, plate=plate, make="Chevrolet", model="Suburban", capacity=5
    )


async def test_one_assignment_per_leg(db: AsyncSession, leg: BookingLeg) -> None:
    driver = Driver(name="Luis", phone="+526240000000")
    db.add(driver)
    await db.flush()
    # Una asignación por unidad: la 1 y la 2 conviven; repetir la 1 no.
    db.add_all(
        [BookingAssignment(leg_id=leg.id, driver_id=driver.id, unit_index=i) for i in (1, 2)]
    )
    await db.flush()
    db.add(BookingAssignment(leg_id=leg.id, driver_id=driver.id, unit_index=1))
    with pytest.raises(IntegrityError, match="uq_booking_assignments_leg_id_unit_index"):
        await db.flush()


async def test_assignment_needs_driver_or_vehicle(db: AsyncSession, leg: BookingLeg) -> None:
    db.add(BookingAssignment(leg_id=leg.id))
    with pytest.raises(IntegrityError, match="ck_booking_assignments_driver_or_vehicle"):
        await db.flush()


async def test_vehicle_plate_unique_per_company(db: AsyncSession, catalog: Catalog) -> None:
    db.add_all([_vehicle(catalog, "BCS-123"), _vehicle(catalog, "BCS-123")])
    with pytest.raises(IntegrityError, match="uq_vehicles_company_id_plate"):
        await db.flush()
