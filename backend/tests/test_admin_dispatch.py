from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, BookingLeg, Driver, EmailOutbox, Vehicle, VehicleClass
from tests.test_admin_auth import PASSWORD, _admin, _csrf_headers
from tests.test_admin_auth import URL as AUTH_URL
from tests.test_booking_access import _bearer
from tests.test_bookings import ARRIVAL, CUSTOMER, _transfer

URL = "/api/v1/admin/dispatch"
BOOKINGS_URL = "/api/v1/bookings"


async def _login(api: AsyncClient, db: AsyncSession) -> dict[str, str]:
    await _admin(db)
    response = await api.post(
        AUTH_URL + "/login", json={"email": "admin@example.com", "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return _csrf_headers(api)


async def _one_way(db: AsyncSession, *, service_time: str, email: str) -> dict[str, Any]:
    return await _transfer(
        db,
        trip_type="one_way",
        direction="arrival",
        legs=[
            {
                "service_date": ARRIVAL.isoformat(),
                "service_time": service_time,
                "flight_number": "aa 1111",
            }
        ],
        customer=CUSTOMER | {"email": email, "confirm_email": email},
    )


async def _leg(db: AsyncSession, code: str) -> BookingLeg:
    leg = await db.scalar(
        select(BookingLeg)
        .join(Booking, Booking.id == BookingLeg.booking_id)
        .where(Booking.code == code)
    )
    assert leg is not None
    return leg


async def _driver(db: AsyncSession, name: str = "Carlos", email: str | None = None) -> Driver:
    driver = Driver(name=name, phone="+52 624 555 0001", email=email)
    db.add(driver)
    await db.flush()
    return driver


async def _vehicle(db: AsyncSession) -> Vehicle:
    vehicle_class_id = await db.scalar(select(VehicleClass.id).limit(1))
    vehicle = Vehicle(
        vehicle_class_id=vehicle_class_id,
        plate="ABC-123",
        make="Chevrolet",
        model="Suburban",
        capacity=6,
    )
    db.add(vehicle)
    await db.flush()
    return vehicle


async def test_board_shows_an_unassigned_leg(api: AsyncClient, db: AsyncSession) -> None:
    created = (
        await api.post(
            BOOKINGS_URL, json=await _one_way(db, service_time="09:00", email="a@example.com")
        )
    ).json()
    headers = await _login(api, db)

    response = await api.get(URL, params={"date": ARRIVAL.isoformat()}, headers=headers)
    assert response.status_code == 200, response.text
    [leg] = [row for row in response.json() if row["booking_code"] == created["code"]]
    assert leg["assignments"] == []


async def test_assign_driver_and_vehicle(api: AsyncClient, db: AsyncSession) -> None:
    created = (
        await api.post(
            BOOKINGS_URL, json=await _one_way(db, service_time="09:00", email="a@example.com")
        )
    ).json()
    headers = await _login(api, db)
    leg = await _leg(db, created["code"])
    driver = await _driver(db)
    vehicle = await _vehicle(db)

    response = await api.post(
        f"{URL}/legs/{leg.id}/assign",
        json={"driver_id": str(driver.id), "vehicle_id": str(vehicle.id)},
        headers=headers,
    )
    assert response.status_code == 200, response.text

    board = (await api.get(URL, params={"date": ARRIVAL.isoformat()}, headers=headers)).json()
    [row] = [r for r in board if r["booking_code"] == created["code"]]
    [assignment] = row["assignments"]
    assert (assignment["driver_name"], assignment["vehicle_plate"]) == ("Carlos", "ABC-123")


async def test_reassigning_replaces_the_existing_assignment(
    api: AsyncClient, db: AsyncSession
) -> None:
    created = (
        await api.post(
            BOOKINGS_URL, json=await _one_way(db, service_time="09:00", email="a@example.com")
        )
    ).json()
    headers = await _login(api, db)
    leg = await _leg(db, created["code"])
    first = await _driver(db, "Carlos")
    second = await _driver(db, "Beto")

    await api.post(
        f"{URL}/legs/{leg.id}/assign", json={"driver_id": str(first.id)}, headers=headers
    )
    await api.post(
        f"{URL}/legs/{leg.id}/assign", json={"driver_id": str(second.id)}, headers=headers
    )

    board = (await api.get(URL, params={"date": ARRIVAL.isoformat()}, headers=headers)).json()
    [row] = [r for r in board if r["booking_code"] == created["code"]]
    [assignment] = row["assignments"]
    assert assignment["driver_name"] == "Beto"


async def test_unassign_removes_the_assignment(api: AsyncClient, db: AsyncSession) -> None:
    created = (
        await api.post(
            BOOKINGS_URL, json=await _one_way(db, service_time="09:00", email="a@example.com")
        )
    ).json()
    headers = await _login(api, db)
    leg = await _leg(db, created["code"])
    driver = await _driver(db)
    await api.post(
        f"{URL}/legs/{leg.id}/assign", json={"driver_id": str(driver.id)}, headers=headers
    )

    response = await api.delete(f"{URL}/legs/{leg.id}/assign", headers=headers)
    assert response.status_code == 204, response.text

    board = (await api.get(URL, params={"date": ARRIVAL.isoformat()}, headers=headers)).json()
    [row] = [r for r in board if r["booking_code"] == created["code"]]
    assert row["assignments"] == []


async def test_invalid_unit_index_is_rejected(api: AsyncClient, db: AsyncSession) -> None:
    created = (
        await api.post(
            BOOKINGS_URL, json=await _one_way(db, service_time="09:00", email="a@example.com")
        )
    ).json()
    headers = await _login(api, db)
    leg = await _leg(db, created["code"])
    driver = await _driver(db)

    response = await api.post(
        f"{URL}/legs/{leg.id}/assign",
        json={"driver_id": str(driver.id), "unit_index": 2},
        headers=headers,
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_unit"


async def test_overlapping_driver_assignment_is_a_conflict(
    api: AsyncClient, db: AsyncSession
) -> None:
    first = (
        await api.post(
            BOOKINGS_URL, json=await _one_way(db, service_time="09:00", email="a@example.com")
        )
    ).json()
    second = (
        await api.post(
            BOOKINGS_URL, json=await _one_way(db, service_time="10:00", email="b@example.com")
        )
    ).json()
    headers = await _login(api, db)
    driver = await _driver(db)

    first_leg = await _leg(db, first["code"])
    ok = await api.post(
        f"{URL}/legs/{first_leg.id}/assign", json={"driver_id": str(driver.id)}, headers=headers
    )
    assert ok.status_code == 200, ok.text

    second_leg = await _leg(db, second["code"])
    conflict = await api.post(
        f"{URL}/legs/{second_leg.id}/assign", json={"driver_id": str(driver.id)}, headers=headers
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "driver_conflict"


async def test_non_overlapping_driver_assignment_is_allowed(
    api: AsyncClient, db: AsyncSession
) -> None:
    first = (
        await api.post(
            BOOKINGS_URL, json=await _one_way(db, service_time="08:00", email="a@example.com")
        )
    ).json()
    second = (
        await api.post(
            BOOKINGS_URL, json=await _one_way(db, service_time="14:00", email="b@example.com")
        )
    ).json()
    headers = await _login(api, db)
    driver = await _driver(db)

    first_leg = await _leg(db, first["code"])
    second_leg = await _leg(db, second["code"])
    ok1 = await api.post(
        f"{URL}/legs/{first_leg.id}/assign", json={"driver_id": str(driver.id)}, headers=headers
    )
    ok2 = await api.post(
        f"{URL}/legs/{second_leg.id}/assign", json={"driver_id": str(driver.id)}, headers=headers
    )
    assert ok1.status_code == ok2.status_code == 200


async def test_cancelled_booking_does_not_appear_on_the_board(
    api: AsyncClient, db: AsyncSession
) -> None:
    created = (
        await api.post(
            BOOKINGS_URL, json=await _one_way(db, service_time="09:00", email="a@example.com")
        )
    ).json()
    await api.post(
        f"{BOOKINGS_URL}/{created['code']}/cancel", json={}, headers=_bearer(created["token"])
    )
    headers = await _login(api, db)

    board = (await api.get(URL, params={"date": ARRIVAL.isoformat()}, headers=headers)).json()
    assert created["code"] not in [row["booking_code"] for row in board]


async def test_assign_requires_csrf_header(api: AsyncClient, db: AsyncSession) -> None:
    created = (
        await api.post(
            BOOKINGS_URL, json=await _one_way(db, service_time="09:00", email="a@example.com")
        )
    ).json()
    await _login(api, db)
    leg = await _leg(db, created["code"])
    driver = await _driver(db)

    response = await api.post(f"{URL}/legs/{leg.id}/assign", json={"driver_id": str(driver.id)})
    assert response.status_code == 403


async def test_assigning_a_driver_with_email_queues_the_notification(
    api: AsyncClient, db: AsyncSession
) -> None:
    """F5.9: aviso al chofer asignado por correo."""
    created = (
        await api.post(
            BOOKINGS_URL, json=await _one_way(db, service_time="09:00", email="a@example.com")
        )
    ).json()
    headers = await _login(api, db)
    leg = await _leg(db, created["code"])
    driver = await _driver(db, email="carlos@example.com")

    response = await api.post(
        f"{URL}/legs/{leg.id}/assign", json={"driver_id": str(driver.id)}, headers=headers
    )
    assert response.status_code == 200, response.text

    board = (await api.get(URL, params={"date": ARRIVAL.isoformat()}, headers=headers)).json()
    [row] = [r for r in board if r["booking_code"] == created["code"]]
    [assignment] = row["assignments"]
    assert assignment["notified_at"] is not None

    email = await db.scalar(select(EmailOutbox).where(EmailOutbox.template == "driver_assigned"))
    assert email is not None
    assert email.to_addresses == ["carlos@example.com"]
    assert email.context["code"] == created["code"]


async def test_assigning_a_driver_without_email_sends_nothing(
    api: AsyncClient, db: AsyncSession
) -> None:
    created = (
        await api.post(
            BOOKINGS_URL, json=await _one_way(db, service_time="09:00", email="a@example.com")
        )
    ).json()
    headers = await _login(api, db)
    leg = await _leg(db, created["code"])
    driver = await _driver(db)  # sin email

    response = await api.post(
        f"{URL}/legs/{leg.id}/assign", json={"driver_id": str(driver.id)}, headers=headers
    )
    assert response.status_code == 200, response.text

    board = (await api.get(URL, params={"date": ARRIVAL.isoformat()}, headers=headers)).json()
    [row] = [r for r in board if r["booking_code"] == created["code"]]
    [assignment] = row["assignments"]
    assert assignment["notified_at"] is None

    email = await db.scalar(select(EmailOutbox).where(EmailOutbox.template == "driver_assigned"))
    assert email is None


async def test_reassigning_to_a_different_driver_notifies_the_new_one(
    api: AsyncClient, db: AsyncSession
) -> None:
    created = (
        await api.post(
            BOOKINGS_URL, json=await _one_way(db, service_time="09:00", email="a@example.com")
        )
    ).json()
    headers = await _login(api, db)
    leg = await _leg(db, created["code"])
    first = await _driver(db, "Carlos", email="carlos@example.com")
    second = await _driver(db, "Beto", email="beto@example.com")

    await api.post(
        f"{URL}/legs/{leg.id}/assign", json={"driver_id": str(first.id)}, headers=headers
    )
    await api.post(
        f"{URL}/legs/{leg.id}/assign", json={"driver_id": str(second.id)}, headers=headers
    )

    emails = (
        await db.scalars(select(EmailOutbox).where(EmailOutbox.template == "driver_assigned"))
    ).all()
    assert sorted(e.to_addresses[0] for e in emails) == ["beto@example.com", "carlos@example.com"]
