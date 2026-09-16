import time
import uuid
from datetime import UTC, date, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Booking,
    BookingLeg,
    BookingSource,
    BookingStatus,
    BookingType,
    Customer,
    Hotel,
    LegStatus,
    LegType,
    VehicleClass,
)
from tests.test_admin_booking_actions import _login
from tests.test_admin_bookings import _create
from tests.test_bookings import _transfer

DASHBOARD_URL = "/api/v1/admin/dashboard"
FINANCE_URL = "/api/v1/admin/finance/summary"
MARKETING_URL = "/api/v1/admin/marketing/kpis"


async def test_dashboard_counts_todays_services_and_unpaid_bookings(
    api: AsyncClient, db: AsyncSession
) -> None:
    created = await _create(api, db)  # tarjeta: pending_payment
    booking = await db.scalar(select(Booking).where(Booking.code == created["code"]))
    assert booking is not None
    service_date = await db.scalar(
        select(BookingLeg.service_date).where(BookingLeg.booking_id == booking.id)
    )
    assert service_date is not None
    headers = await _login(api, db)

    response = await api.get(
        DASHBOARD_URL, params={"date": service_date.isoformat()}, headers=headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["today_services"] >= 1
    assert body["unassigned_legs"] >= 1
    assert body["unpaid_bookings"] >= 1


async def test_finance_summary_reflects_a_confirmed_booking(
    api: AsyncClient, db: AsyncSession
) -> None:
    body = await _transfer(db, payment="cash")
    created = (await api.post("/api/v1/bookings", json=body)).json()
    assert created["status"] == "confirmed"
    headers = await _login(api, db)

    response = await api.get(FINANCE_URL, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["revenue_30d_cents"] >= created["total_cents"]


async def test_marketing_kpis_counts_todays_bookings(api: AsyncClient, db: AsyncSession) -> None:
    await _create(api, db)
    headers = await _login(api, db)

    response = await api.get(MARKETING_URL, headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["bookings_today"] >= 1
    assert body["bookings_this_month"] >= 1
    assert body["top_zone"] is not None


async def _bulk_seed_bookings(db: AsyncSession, count: int) -> None:
    """Inserta reservas directo con Core, sin pasar por la API: 10 000 HTTP serían el cuello
    de botella de la prueba, no la consulta que en realidad se quiere medir (F6.11).
    """
    company_id = db.info["company_id"]
    customer_id = uuid.uuid4()
    await db.execute(
        insert(Customer).values(
            id=customer_id,
            company_id=company_id,
            name="Load Test",
            email="load-test@example.com",
            phone="+52 624 000 0000",
        )
    )
    hotel_id = await db.scalar(select(Hotel.id).where(Hotel.slug == "one-and-only-palmilla"))
    vehicle_class_id = await db.scalar(
        select(VehicleClass.id).where(VehicleClass.code == "SUBURBAN")
    )

    now = datetime.now(UTC)
    today = date.today()
    bookings = []
    legs = []
    for i in range(count):
        booking_id = uuid.uuid4()
        created_at = now - timedelta(days=i % 40)
        bookings.append(
            {
                "id": booking_id,
                "company_id": company_id,
                "code": f"CTC-LOAD-{i:06d}",
                "status": BookingStatus.CONFIRMED,
                "source": BookingSource.WEBSITE,
                "booking_type": BookingType.TRANSFER,
                "customer_id": customer_id,
                "language": "en",
                "currency": "USD",
                "subtotal_cents": 10000,
                "discount_cents": 0,
                "tax_cents": 1600,
                "total_cents": 11600,
                "deposit_cents": 0,
                "created_at": created_at,
                "updated_at": created_at,
            }
        )
        legs.append(
            {
                "id": uuid.uuid4(),
                "company_id": company_id,
                "booking_id": booking_id,
                "leg_type": LegType.ARRIVAL,
                "status": LegStatus.SCHEDULED,
                "service_date": today + timedelta(days=i % 5),
                "origin": "SJD Los Cabos International Airport",
                "destination": "One and Only Palmilla",
                "hotel_id": hotel_id,
                "pax_adults": 2,
                "pax_children": 0,
                "vehicle_class_id": vehicle_class_id,
                "vehicle_count": 1,
            }
        )
    await db.execute(insert(Booking), bookings)
    await db.execute(insert(BookingLeg), legs)


async def test_dashboard_is_fast_with_ten_thousand_bookings(
    api: AsyncClient, db: AsyncSession
) -> None:
    """Criterio de F6.11: < 300 ms con 10 000 reservas de prueba."""
    await _bulk_seed_bookings(db, 10_000)
    headers = await _login(api, db)
    params = {"date": date.today().isoformat()}

    # La primera petición de la suite paga ~200 ms de arranque (compilar los statements de
    # SQLAlchemy, armar el response_model): un costo fijo que no depende de las 10 000 reservas.
    # Medirlo hacía fallar el test por azar; lo que interesa es el estado caliente.
    warmup = await api.get(DASHBOARD_URL, params=params, headers=headers)
    assert warmup.status_code == 200, warmup.text

    start = time.perf_counter()
    response = await api.get(DASHBOARD_URL, params=params, headers=headers)
    elapsed = time.perf_counter() - start

    assert response.status_code == 200, response.text
    assert elapsed < 0.3, f"dashboard took {elapsed:.3f}s with 10 000 bookings"
