from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminRole
from tests.test_admin_auth import PASSWORD, _admin
from tests.test_admin_auth import URL as AUTH_URL
from tests.test_bookings import CUSTOMER, _transfer

URL = "/api/v1/admin/bookings"


async def _login(api: AsyncClient, db: AsyncSession) -> None:
    await _admin(db, role=AdminRole.DISPATCHER)
    response = await api.post(
        AUTH_URL + "/login", json={"email": "admin@example.com", "password": PASSWORD}
    )
    assert response.status_code == 200, response.text


async def _create(api: AsyncClient, db: AsyncSession, **changes: Any) -> dict[str, Any]:
    response = await api.post("/api/v1/bookings", json=await _transfer(db, **changes))
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


async def test_requires_authentication(api: AsyncClient) -> None:
    response = await api.get(URL)
    assert response.status_code == 401


async def test_a_new_card_booking_appears_in_the_default_listing(
    api: AsyncClient, db: AsyncSession
) -> None:
    """Criterio de F6.4: sin filtro de estado, una reserva recién creada siempre aparece."""
    created = await _create(api, db)
    await _login(api, db)

    response = await api.get(URL)
    assert response.status_code == 200, response.text
    body = response.json()
    codes = [item["code"] for item in body["items"]]
    assert created["code"] in codes
    assert body["total"] >= 1


async def test_a_cash_no_deposit_booking_confirmed_on_the_spot_also_appears(
    api: AsyncClient, db: AsyncSession
) -> None:
    created = await _create(api, db, payment="cash")
    assert created["status"] == "confirmed"
    await _login(api, db)

    response = await api.get(URL)
    codes = [item["code"] for item in response.json()["items"]]
    assert created["code"] in codes


async def test_status_filter_narrows_the_results(api: AsyncClient, db: AsyncSession) -> None:
    card = await _create(
        api,
        db,
        customer=CUSTOMER | {"email": "card@example.com", "confirm_email": "card@example.com"},
    )
    cash = await _create(
        api,
        db,
        payment="cash",
        customer=CUSTOMER | {"email": "cash@example.com", "confirm_email": "cash@example.com"},
    )
    await _login(api, db)

    pending = await api.get(URL, params={"status": "pending_payment"})
    pending_codes = [item["code"] for item in pending.json()["items"]]
    assert card["code"] in pending_codes
    assert cash["code"] not in pending_codes

    confirmed = await api.get(URL, params={"status": "confirmed"})
    confirmed_codes = [item["code"] for item in confirmed.json()["items"]]
    assert cash["code"] in confirmed_codes
    assert card["code"] not in confirmed_codes


async def test_search_matches_code_name_email_phone_and_flight(
    api: AsyncClient, db: AsyncSession
) -> None:
    created = await _create(api, db)
    await _login(api, db)

    for q in (created["code"], "López", "ana@example.com", "624 111 2222", "AA1245"):
        response = await api.get(URL, params={"q": q})
        codes = [item["code"] for item in response.json()["items"]]
        assert created["code"] in codes, f"query {q!r} did not find the booking"

    miss = await api.get(URL, params={"q": "nobody-books-this"})
    assert miss.json()["items"] == []


async def test_zone_filter_matches_the_hotel_zone(api: AsyncClient, db: AsyncSession) -> None:
    created = await _create(api, db)  # One&Only Palmilla está en the-corridor
    await _login(api, db)

    hit = await api.get(URL, params={"zone": "the-corridor"})
    assert created["code"] in [item["code"] for item in hit.json()["items"]]

    miss = await api.get(URL, params={"zone": "cabo-san-lucas"})
    assert created["code"] not in [item["code"] for item in miss.json()["items"]]


async def test_pagination_pages_through_the_results(api: AsyncClient, db: AsyncSession) -> None:
    emails = ["a@example.com", "b@example.com", "c@example.com"]
    for email in emails:
        await _create(api, db, customer=CUSTOMER | {"email": email, "confirm_email": email})
    await _login(api, db)

    first = await api.get(URL, params={"page": 1, "page_size": 2})
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert len(first_body["items"]) == 2
    assert first_body["total"] >= 3

    second = await api.get(URL, params={"page": 2, "page_size": 2})
    second_body = second.json()
    first_codes = {item["code"] for item in first_body["items"]}
    second_codes = {item["code"] for item in second_body["items"]}
    assert first_codes.isdisjoint(second_codes)


async def test_sort_by_total_cents_ascending(api: AsyncClient, db: AsyncSession) -> None:
    cheap = await _create(
        api,
        db,
        passengers=1,
        customer=CUSTOMER | {"email": "cheap@example.com", "confirm_email": "cheap@example.com"},
    )
    pricey = await _create(
        api,
        db,
        passengers=6,
        customer=CUSTOMER | {"email": "pricey@example.com", "confirm_email": "pricey@example.com"},
    )
    assert cheap["total_cents"] < pricey["total_cents"]
    await _login(api, db)

    response = await api.get(URL, params={"sort": "total_cents", "order": "asc"})
    codes = [item["code"] for item in response.json()["items"]]
    assert codes.index(cheap["code"]) < codes.index(pricey["code"])
