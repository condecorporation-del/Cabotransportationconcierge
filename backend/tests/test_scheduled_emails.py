import uuid
from datetime import date, datetime, time, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Booking,
    BookingAssignment,
    BookingLeg,
    BookingSource,
    BookingStatus,
    BookingType,
    CompanySettings,
    Customer,
    EmailOutbox,
    Hotel,
    LegStatus,
    LegType,
    VehicleClass,
)
from app.worker.scheduled import pickup_at, request_reviews, send_reminders
from tests.test_admin_dispatch import _driver, _vehicle

REVIEW_URL = "https://g.page/r/cabo-transportation-concierge/review"


@pytest.fixture(autouse=True)
async def _seeded(api: AsyncClient) -> None:
    """Estos trabajos no pasan por HTTP, pero sí necesitan el catálogo real: la fixture
    `api` es la que siembra la empresa, sus ajustes, los hoteles y las clases."""


async def _booking(
    db: AsyncSession,
    *,
    service_date: date,
    pickup_time: time | None = time(10, 0),
    status: BookingStatus = BookingStatus.CONFIRMED,
    leg_status: LegStatus = LegStatus.SCHEDULED,
) -> tuple[Booking, BookingLeg]:
    suffix = uuid.uuid4().hex[:8]
    customer = Customer(
        name="Ana Guest", email=f"ana-{suffix}@example.com", phone="+52 624 000 0000"
    )
    db.add(customer)
    await db.flush()
    booking = Booking(
        code=f"CTC-SCHED-{suffix}",
        status=status,
        source=BookingSource.WEBSITE,
        booking_type=BookingType.TRANSFER,
        customer_id=customer.id,
        language="en",
        currency="USD",
        subtotal_cents=10000,
        tax_cents=1600,
        total_cents=11600,
    )
    db.add(booking)
    await db.flush()
    leg = BookingLeg(
        booking_id=booking.id,
        leg_type=LegType.ARRIVAL,
        status=leg_status,
        service_date=service_date,
        pickup_time=pickup_time,
        origin="SJD Los Cabos International Airport",
        destination="One and Only Palmilla",
        hotel_id=await db.scalar(select(Hotel.id).where(Hotel.slug == "one-and-only-palmilla")),
        pax_adults=2,
        vehicle_class_id=await db.scalar(
            select(VehicleClass.id).where(VehicleClass.code == "SUBURBAN")
        ),
    )
    db.add(leg)
    await db.flush()
    return booking, leg


async def _queued(db: AsyncSession, template: str, booking: Booking) -> list[EmailOutbox]:
    rows = await db.scalars(
        select(EmailOutbox).where(
            EmailOutbox.template == template, EmailOutbox.booking_id == booking.id
        )
    )
    return list(rows)


async def _configure_review_link(db: AsyncSession, url: str | None = REVIEW_URL) -> None:
    settings = await db.scalar(
        select(CompanySettings).where(CompanySettings.company_id == db.info["company_id"])
    )
    assert settings is not None
    settings.social_links = {"google_review": url} if url else {}
    await db.flush()


def _company_timezone_now(leg: BookingLeg, offset: timedelta) -> datetime:
    return pickup_at(leg, "America/Mazatlan") + offset


async def test_reminder_goes_out_inside_the_last_day(db: AsyncSession) -> None:
    booking, leg = await _booking(db, service_date=date.today() + timedelta(days=1))

    sent = await send_reminders(db, _company_timezone_now(leg, -timedelta(hours=20)))

    assert sent == 1
    emails = await _queued(db, "booking_reminder", booking)
    assert len(emails) == 1
    assert emails[0].context["code"] == booking.code
    assert emails[0].context["pickup_time"] == "10:00"
    assert leg.reminder_sent_at is not None


async def test_reminder_waits_until_the_day_before(db: AsyncSession) -> None:
    booking, leg = await _booking(db, service_date=date.today() + timedelta(days=2))

    sent = await send_reminders(db, _company_timezone_now(leg, -timedelta(hours=40)))

    assert sent == 0
    assert await _queued(db, "booking_reminder", booking) == []
    assert leg.reminder_sent_at is None


async def test_reminder_is_sent_once_per_leg(db: AsyncSession) -> None:
    booking, leg = await _booking(db, service_date=date.today() + timedelta(days=1))
    now = _company_timezone_now(leg, -timedelta(hours=20))

    assert await send_reminders(db, now) == 1
    assert await send_reminders(db, now + timedelta(minutes=15)) == 0

    assert len(await _queued(db, "booking_reminder", booking)) == 1


async def test_reminder_carries_the_assigned_driver_and_vehicle(db: AsyncSession) -> None:
    booking, leg = await _booking(db, service_date=date.today() + timedelta(days=1))
    driver = await _driver(db, name="Carlos Nuñez")
    vehicle = await _vehicle(db)
    db.add(BookingAssignment(leg_id=leg.id, driver_id=driver.id, vehicle_id=vehicle.id))
    await db.flush()

    await send_reminders(db, _company_timezone_now(leg, -timedelta(hours=20)))

    crew = (await _queued(db, "booking_reminder", booking))[0].context["crew"]
    assert "Carlos Nuñez" in crew
    assert "ABC-123" in crew


async def test_cancelled_booking_gets_no_reminder(db: AsyncSession) -> None:
    booking, leg = await _booking(
        db,
        service_date=date.today() + timedelta(days=1),
        status=BookingStatus.CANCELLED,
        leg_status=LegStatus.CANCELLED,
    )

    assert await send_reminders(db, _company_timezone_now(leg, -timedelta(hours=20))) == 0
    assert await _queued(db, "booking_reminder", booking) == []


async def test_review_is_requested_once_after_the_service(db: AsyncSession) -> None:
    await _configure_review_link(db)
    booking, leg = await _booking(db, service_date=date.today())
    now = _company_timezone_now(leg, timedelta(hours=6))

    assert await request_reviews(db, now) == 1
    assert await request_reviews(db, now + timedelta(hours=1)) == 0

    emails = await _queued(db, "review_request", booking)
    assert len(emails) == 1
    assert emails[0].context["review_url"] == REVIEW_URL
    assert booking.review_requested_at is not None


async def test_review_waits_until_the_trip_is_over(db: AsyncSession) -> None:
    await _configure_review_link(db)
    booking, leg = await _booking(db, service_date=date.today())

    assert await request_reviews(db, _company_timezone_now(leg, timedelta(hours=1))) == 0
    assert await _queued(db, "review_request", booking) == []


async def test_review_needs_a_configured_link(db: AsyncSession) -> None:
    await _configure_review_link(db, url=None)
    booking, leg = await _booking(db, service_date=date.today())

    assert await request_reviews(db, _company_timezone_now(leg, timedelta(hours=6))) == 0
    assert await _queued(db, "review_request", booking) == []
    # Sin marcar: el correo tiene que salir solo en cuanto el admin configure el enlace.
    assert booking.review_requested_at is None


async def test_old_trips_are_not_asked_for_a_review(db: AsyncSession) -> None:
    await _configure_review_link(db)
    booking, leg = await _booking(db, service_date=date.today() - timedelta(days=20))

    assert await request_reviews(db, _company_timezone_now(leg, timedelta(days=40))) == 0
    assert await _queued(db, "review_request", booking) == []
