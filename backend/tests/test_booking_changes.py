from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, BookingLeg, CompanySettings, LegStatus
from tests.test_booking_access import _bearer, _book
from tests.test_bookings import URL


async def test_customer_changes_flight_time_and_notes(api: AsyncClient, db: AsyncSession) -> None:
    created = await _book(api, db)
    body = {
        "legs": [{"leg_type": "departure", "service_time": "12:30", "flight_number": "dl 590"}],
        "notes": "Two surfboards",
    }
    url = f"{URL}/{created['code']}"
    response = await api.patch(url, json=body, headers=_bearer(created["token"]))
    assert response.status_code == 200, response.text
    changed = response.json()
    [departure] = [leg for leg in changed["legs"] if leg["leg_type"] == "departure"]
    # Salida internacional: el pickup se mueve con el vuelo y conserva las 3 h.
    assert (departure["service_time"], departure["pickup_time"], departure["flight_number"]) == (
        "12:30:00",
        "09:30:00",
        "DL590",
    )
    assert changed["notes_customer"] == "Two surfboards"
    log = await db.scalar(select(AuditLog).where(AuditLog.action == "customer_change"))
    assert log is not None
    assert log.before["departure"]["pickup_time"] == "08:00:00"


async def test_new_time_that_changes_the_price_is_refused(
    api: AsyncClient, db: AsyncSession
) -> None:
    created = await _book(api, db)
    body = {"legs": [{"leg_type": "arrival", "service_time": "23:30"}]}
    url = f"{URL}/{created['code']}"
    response = await api.patch(url, json=body, headers=_bearer(created["token"]))
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "price_change"


async def test_changes_and_cancellation_close_before_the_service(
    api: AsyncClient, db: AsyncSession
) -> None:
    created = await _book(api, db)
    await db.execute(
        update(CompanySettings).values(change_hours=24 * 365, cancellation_hours=24 * 365)
    )
    url, headers = f"{URL}/{created['code']}", _bearer(created["token"])
    change = await api.patch(
        url, json={"legs": [{"leg_type": "arrival", "airline": "Delta"}]}, headers=headers
    )
    cancel = await api.post(f"{url}/cancel", json={}, headers=headers)
    assert [change.json()["detail"]["code"], cancel.json()["detail"]["code"]] == [
        "change_window",
        "cancel_window",
    ]


async def test_cancelled_booking_cannot_be_cancelled_or_changed_again(
    api: AsyncClient, db: AsyncSession
) -> None:
    created = await _book(api, db)
    url, headers = f"{URL}/{created['code']}", _bearer(created["token"])
    first = await api.post(f"{url}/cancel", json={"reason": "Trip postponed"}, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "cancelled"
    assert {leg.status for leg in (await db.scalars(select(BookingLeg))).all()} == {
        LegStatus.CANCELLED
    }

    again = await api.post(f"{url}/cancel", json={}, headers=headers)
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "invalid_transition"
    change = await api.patch(url, json={"notes": "Still coming"}, headers=headers)
    assert change.json()["detail"]["code"] == "not_editable"
