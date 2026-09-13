from datetime import date, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, BookingItem, BookingLeg, Customer, Hotel, LegType, Rate

ARRIVAL = date.today() + timedelta(days=30)
URL = "/api/v1/bookings"


async def _transfer(db: AsyncSession, **changes: Any) -> dict[str, Any]:
    hotel_id = await db.scalar(select(Hotel.id).where(Hotel.slug == "one-and-only-palmilla"))
    return {
        "type": "transfer",
        "hotel_id": str(hotel_id),
        "trip_type": "round_trip",
        "passengers": 3,
        "legs": [
            {
                "service_date": ARRIVAL.isoformat(),
                "service_time": "13:20",
                "flight_number": "AA1245",
            },
            {"service_date": (ARRIVAL + timedelta(days=5)).isoformat(), "service_time": "11:00"},
        ],
        "extras": [{"code": "BABY_SEAT", "quantity": 1}],
        "customer": {"name": "Ana López", "email": "ana@example.com"},
    } | changes


async def test_round_trip_booking_is_created_with_frozen_prices(
    api: AsyncClient, db: AsyncSession
) -> None:
    response = await api.post(URL, json=await _transfer(db))
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["code"].startswith(f"CTC-{date.today().year}-")
    assert created["status"] == "pending_payment"
    assert sum(item["total_cents"] for item in created["items"]) == created["total_cents"]

    legs = (await db.scalars(select(BookingLeg).order_by(BookingLeg.service_date))).all()
    assert [(leg.leg_type, leg.destination) for leg in legs] == [
        (LegType.ARRIVAL, "One and Only Palmilla"),
        (LegType.DEPARTURE, "SJD Los Cabos International Airport"),
    ]
    assert legs[0].flight_number == "AA1245"


async def test_same_idempotency_key_creates_one_booking(api: AsyncClient, db: AsyncSession) -> None:
    body = await _transfer(db)
    headers = {"Idempotency-Key": "checkout-7f3a9c21"}
    first = await api.post(URL, json=body, headers=headers)
    second = await api.post(URL, json=body, headers=headers)
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert await db.scalar(select(func.count()).select_from(Booking)) == 1


async def test_customer_is_reused_by_email_without_losing_data(
    api: AsyncClient, db: AsyncSession
) -> None:
    await api.post(URL, json=await _transfer(db))
    returning = {"name": "Otro", "email": "ANA@example.com", "phone": "+52 624 000 0000"}
    response = await api.post(URL, json=await _transfer(db, customer=returning))
    assert response.status_code == 201, response.text
    [customer] = (await db.scalars(select(Customer))).all()
    await db.refresh(customer)
    assert (customer.name, customer.phone) == ("Ana López", "+52 624 000 0000")


async def test_one_way_departure(api: AsyncClient, db: AsyncSession) -> None:
    body = await _transfer(
        db,
        trip_type="one_way",
        direction="departure",
        legs=[{"service_date": ARRIVAL.isoformat(), "service_time": "08:00"}],
    )
    assert (await api.post(URL, json=body)).status_code == 201
    [leg] = (await db.scalars(select(BookingLeg))).all()
    assert (leg.leg_type, leg.origin) == (LegType.DEPARTURE, "One and Only Palmilla")


async def test_activity_booking_keeps_park_fee_out_of_the_total(
    api: AsyncClient, db: AsyncSession
) -> None:
    [package, *_] = (await api.get("/api/v1/catalog/packages")).json()
    activities = [a["slug"] for a in (await api.get("/api/v1/catalog/activities")).json()]
    body = {
        "type": "activity",
        "package": package["slug"],
        "activities": activities[: package["activity_count"]],
        "guests": 2,
        "service_date": ARRIVAL.isoformat(),
        "customer": {"name": "Ana López", "email": "ana@example.com"},
    }
    response = await api.post(URL, json=body)
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["total_cents"] == package["price_per_person_cents"] * 2
    kinds = [item["item_type"] for item in created["items"]]
    assert package["park_fee_cents"] > 0
    assert kinds == ["activity", "park_fee"]
    assert created["items"][1]["total_cents"] == package["park_fee_cents"] * 2


async def test_rate_change_does_not_touch_existing_bookings(
    api: AsyncClient, db: AsyncSession
) -> None:
    """F2.8: el precio queda congelado en booking_items."""
    await api.post(URL, json=await _transfer(db))
    before = (await db.scalars(select(BookingItem.total_cents).order_by(BookingItem.id))).all()
    await db.execute(update(Rate).values(price_cents=Rate.price_cents + 5000))
    after = (await db.scalars(select(BookingItem.total_cents).order_by(BookingItem.id))).all()
    assert before == after


async def test_client_cannot_send_prices_or_local_scope(api: AsyncClient, db: AsyncSession) -> None:
    priced = await api.post(URL, json=await _transfer(db, total_cents=1))
    assert priced.status_code == 422
    local = await api.post(URL, json=await _transfer(db, service_scope="local"))
    assert local.status_code == 422
    assert local.json()["detail"]["code"] == "scope_unavailable"
    assert await db.scalar(select(func.count()).select_from(Booking)) == 0
