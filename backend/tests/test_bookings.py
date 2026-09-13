from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AuditActor,
    AuditLog,
    Booking,
    BookingItem,
    BookingLeg,
    Customer,
    Hotel,
    LegType,
    Rate,
)

ARRIVAL = date.today() + timedelta(days=30)
URL = "/api/v1/bookings"
CUSTOMER = {
    "first_name": "Ana",
    "last_name": "López",
    "email": "ana@example.com",
    "confirm_email": "ana@example.com",
    "phone": "+52 624 111 2222",
}


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
                "flight_number": "aa 1245",
            },
            {"service_date": (ARRIVAL + timedelta(days=5)).isoformat(), "service_time": "11:00"},
        ],
        "extras": [{"code": "CAR_SEAT", "quantity": 2}],
        "customer": CUSTOMER,
        "accepted_terms_version": "1",
    } | changes


async def test_round_trip_booking_is_created_with_frozen_prices(
    api: AsyncClient, db: AsyncSession
) -> None:
    response = await api.post(URL, json=await _transfer(db))
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["code"].startswith(f"CTC-{date.today().year}-")
    assert created["status"] == "pending_payment"
    items = sum(item["total_cents"] for item in created["items"])
    assert items + created["tax_cents"] == created["total_cents"]

    legs = (await db.scalars(select(BookingLeg).order_by(BookingLeg.service_date))).all()
    assert [(leg.leg_type, leg.destination) for leg in legs] == [
        (LegType.ARRIVAL, "One and Only Palmilla"),
        (LegType.DEPARTURE, "SJD Los Cabos International Airport"),
    ]
    assert legs[0].flight_number == "AA1245"


async def test_large_group_books_several_vehicles(api: AsyncClient, db: AsyncSession) -> None:
    body = await _transfer(db, passengers=12, vehicle_class="SUBURBAN", extras=[])
    response = await api.post(URL, json=body)
    assert response.status_code == 201, response.text
    assert response.json()["items"][0]["quantity"] == 3
    legs = (await db.scalars(select(BookingLeg))).all()
    assert {leg.vehicle_count for leg in legs} == {3}


async def test_booking_keeps_attribution_and_is_audited(api: AsyncClient, db: AsyncSession) -> None:
    """F3.11 y F3.9."""
    attribution = {
        "utm_source": "instagram",
        "utm_campaign": "september",
        "referrer": "https://www.instagram.com/",
    }
    created = (await api.post(URL, json=await _transfer(db, attribution=attribution))).json()
    booking = await db.scalar(select(Booking).where(Booking.code == created["code"]))
    assert booking is not None
    assert booking.utm == attribution
    log = await db.scalar(select(AuditLog).where(AuditLog.entity_id == booking.id))
    assert log is not None
    assert (log.actor, log.action, log.after["code"]) == (
        AuditActor.CUSTOMER,
        "create",
        created["code"],
    )


async def test_same_idempotency_key_creates_one_booking(api: AsyncClient, db: AsyncSession) -> None:
    body = await _transfer(db)
    headers = {"Idempotency-Key": "checkout-7f3a9c21"}
    first = await api.post(URL, json=body, headers=headers)
    second = await api.post(URL, json=body, headers=headers)
    assert first.status_code == second.status_code == 201
    replies = [first.json(), second.json()]
    assert all(reply.pop("token") for reply in replies)
    assert replies[0] == replies[1]
    assert await db.scalar(select(func.count()).select_from(Booking)) == 1


async def test_customer_is_reused_by_email_without_losing_data(
    api: AsyncClient, db: AsyncSession
) -> None:
    await api.post(URL, json=await _transfer(db))
    returning = CUSTOMER | {
        "first_name": "Otro",
        "email": "ANA@example.com",
        "confirm_email": "ANA@example.com",
        "phone": "+52 624 999 9999",
        "country": "MX",
    }
    response = await api.post(URL, json=await _transfer(db, customer=returning))
    assert response.status_code == 201, response.text
    [customer] = (await db.scalars(select(Customer))).all()
    await db.refresh(customer)
    # El nombre y el teléfono ya guardados no se pisan; el país, que faltaba, sí se completa.
    assert (customer.name, customer.phone, customer.country) == (
        "Ana López",
        "+52 624 111 2222",
        "MX",
    )


async def test_one_way_departure(api: AsyncClient, db: AsyncSession) -> None:
    body = await _transfer(
        db,
        trip_type="one_way",
        direction="departure",
        legs=[
            {"service_date": ARRIVAL.isoformat(), "service_time": "08:00", "international": False}
        ],
    )
    assert (await api.post(URL, json=body)).status_code == 201
    [leg] = (await db.scalars(select(BookingLeg))).all()
    assert (leg.leg_type, leg.origin) == (LegType.DEPARTURE, "One and Only Palmilla")
    assert (leg.service_date, leg.pickup_time) == (ARRIVAL, time(6, 0))


async def test_international_pickup_can_fall_the_day_before(
    api: AsyncClient, db: AsyncSession
) -> None:
    body = await _transfer(
        db,
        trip_type="one_way",
        direction="departure",
        legs=[{"service_date": ARRIVAL.isoformat(), "service_time": "01:30"}],
    )
    assert (await api.post(URL, json=body)).status_code == 201
    [leg] = (await db.scalars(select(BookingLeg))).all()
    assert (leg.service_date, leg.pickup_time, leg.service_time) == (
        ARRIVAL - timedelta(days=1),
        time(22, 30),
        time(1, 30),
    )


async def test_customer_pickup_time_override_is_used_instead_of_the_suggestion(
    api: AsyncClient, db: AsyncSession
) -> None:
    """F3.12: la hora sugerida (2 h antes, nacional) se puede editar."""
    body = await _transfer(
        db,
        trip_type="one_way",
        direction="departure",
        legs=[
            {
                "service_date": ARRIVAL.isoformat(),
                "service_time": "12:00",
                "international": False,
                "pickup_time": "09:30",
            }
        ],
    )
    assert (await api.post(URL, json=body)).status_code == 201
    [leg] = (await db.scalars(select(BookingLeg))).all()
    assert leg.pickup_time == time(9, 30)


async def test_confirm_email_must_match(api: AsyncClient, db: AsyncSession) -> None:
    customer = CUSTOMER | {"confirm_email": "otro@example.com"}
    response = await api.post(URL, json=await _transfer(db, customer=customer))
    assert response.status_code == 422
    assert "Emails don't match" in response.text


async def test_phone_is_required_and_has_a_minimum_length(
    api: AsyncClient, db: AsyncSession
) -> None:
    too_short = await api.post(URL, json=await _transfer(db, customer=CUSTOMER | {"phone": "123"}))
    assert too_short.status_code == 422
    missing_customer = {key: value for key, value in CUSTOMER.items() if key != "phone"}
    missing = await api.post(URL, json=await _transfer(db, customer=missing_customer))
    assert missing.status_code == 422


async def test_outdated_terms_version_is_rejected(api: AsyncClient, db: AsyncSession) -> None:
    response = await api.post(URL, json=await _transfer(db, accepted_terms_version="0"))
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "terms_outdated"


async def test_cash_payment_confirms_without_deposit(api: AsyncClient, db: AsyncSession) -> None:
    """F3.13: efectivo sin depósito confirma sin pago en línea; con depósito sigue pendiente."""
    no_deposit = await api.post(URL, json=await _transfer(db, payment="cash"))
    assert no_deposit.status_code == 201, no_deposit.text
    created = no_deposit.json()
    assert (created["status"], created["payment_method"], created["tax_cents"]) == (
        "confirmed",
        "cash",
        0,
    )

    with_deposit = await api.post(
        URL, json=await _transfer(db, payment="cash", vehicle_class="ESCALADE")
    )
    assert with_deposit.json()["status"] == "pending_payment"

    card = await api.post(URL, json=await _transfer(db, payment="card"))
    assert (card.json()["status"], card.json()["payment_method"]) == ("pending_payment", "card")


async def test_schedule_rules_have_stable_codes(api: AsyncClient, db: AsyncSession) -> None:
    soon = datetime.now(ZoneInfo("America/Mazatlan")) + timedelta(hours=2)
    cases = {
        "too_soon": [{"service_date": soon.date().isoformat(), "service_time": f"{soon:%H:%M}"}],
        "time_required": [{"service_date": ARRIVAL.isoformat()}],
    }
    for code, legs in cases.items():
        response = await api.post(URL, json=await _transfer(db, trip_type="one_way", legs=legs))
        assert response.status_code == 422, code
        assert response.json()["detail"]["code"] == code


@pytest.mark.parametrize(
    ("flight", "return_time"), [("12345678", "11:00"), ("AA1245", "09:00")], ids=["flight", "order"]
)
async def test_invalid_flight_or_return_before_arrival(
    api: AsyncClient, db: AsyncSession, flight: str, return_time: str
) -> None:
    day = ARRIVAL.isoformat()
    legs = [
        {"service_date": day, "service_time": "13:20", "flight_number": flight},
        {"service_date": day, "service_time": return_time},
    ]
    response = await api.post(URL, json=await _transfer(db, legs=legs))
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


async def test_late_arrival_adds_night_surcharge(api: AsyncClient, db: AsyncSession) -> None:
    """F3.4: el recargo nocturno sale del motor y queda como ítem de la reserva."""
    body = await _transfer(
        db,
        trip_type="one_way",
        legs=[{"service_date": ARRIVAL.isoformat(), "service_time": "23:10"}],
    )
    skip = {"customer", "accepted_terms_version"}
    request = {key: value for key, value in body.items() if key not in skip}
    quote = (await api.post("/api/v1/quotes", json=request)).json()
    assert "NIGHT_SURCHARGE" in [line["code"] for line in quote["lines"]]
    created = (await api.post(URL, json=body)).json()
    assert len(created["items"]) == len(quote["lines"])
    assert created["total_cents"] == quote["total_cents"]


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
        "customer": CUSTOMER,
        "accepted_terms_version": "1",
    }
    response = await api.post(URL, json=body)
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["total_cents"] == package["price_per_person_cents"] * 2
    kinds = [item["item_type"] for item in created["items"]]
    assert {item["service_date"] for item in created["items"]} == {ARRIVAL.isoformat()}
    assert package["park_fee_cents"] > 0
    assert kinds == ["activity", "park_fee"]
    assert created["items"][1]["total_cents"] == package["park_fee_cents"] * 2

    today = datetime.now(ZoneInfo("America/Mazatlan")).date().isoformat()
    same_day = await api.post(URL, json=body | {"service_date": today})
    assert same_day.json()["detail"]["code"] == "too_soon"


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
