from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AccountCharge, ClientAccount, Customer, Hotel
from tests.test_admin_booking_actions import _login
from tests.test_bookings import ARRIVAL, CUSTOMER

URL = "/api/v1/admin/bookings"


async def _manual_body(db: AsyncSession, **changes: Any) -> dict[str, Any]:
    hotel_id = await db.scalar(select(Hotel.id).where(Hotel.slug == "one-and-only-palmilla"))
    return {
        "hotel_id": str(hotel_id),
        "trip_type": "one_way",
        "direction": "arrival",
        "passengers": 2,
        "payment": "none",
        "legs": [
            {
                "service_date": ARRIVAL.isoformat(),
                "service_time": "13:20",
                "flight_number": "aa 1245",
            }
        ],
        "customer": CUSTOMER,
    } | changes


async def test_none_creates_an_offline_hold(api: AsyncClient, db: AsyncSession) -> None:
    headers = await _login(api, db)
    response = await api.post(URL, json=await _manual_body(db), headers=headers)
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "offline_hold"


async def test_cash_confirms_directly(api: AsyncClient, db: AsyncSession) -> None:
    headers = await _login(api, db)
    response = await api.post(URL, json=await _manual_body(db, payment="cash"), headers=headers)
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "confirmed"


async def test_stripe_is_pending_payment_and_taxed_like_card(
    api: AsyncClient, db: AsyncSession
) -> None:
    headers = await _login(api, db)
    stripe = await api.post(URL, json=await _manual_body(db, payment="stripe"), headers=headers)
    assert stripe.status_code == 201, stripe.text
    assert stripe.json()["status"] == "pending_payment"

    card_equivalent = await api.post(
        URL,
        json=await _manual_body(
            db,
            payment="stripe",
            customer=CUSTOMER
            | {"email": "other@example.com", "confirm_email": "other@example.com"},
        ),
        headers=headers,
    )
    assert stripe.json()["tax_cents"] == card_equivalent.json()["tax_cents"] > 0


async def test_account_confirms_and_creates_a_charge(api: AsyncClient, db: AsyncSession) -> None:
    customer = Customer(name="Ana López", email="acct@example.com", phone="+52 624 111 2222")
    db.add(customer)
    await db.flush()
    account = ClientAccount(customer_id=customer.id, name="Ana's account")
    db.add(account)
    await db.flush()
    headers = await _login(api, db)

    body = await _manual_body(
        db,
        payment="account",
        account_id=str(account.id),
        customer=CUSTOMER | {"email": "acct@example.com", "confirm_email": "acct@example.com"},
    )
    response = await api.post(URL, json=body, headers=headers)
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "confirmed"

    [charge] = (
        await db.scalars(select(AccountCharge).where(AccountCharge.account_id == account.id))
    ).all()
    assert charge.amount_cents == response.json()["total_cents"]


async def test_account_without_account_id_is_rejected(api: AsyncClient, db: AsyncSession) -> None:
    headers = await _login(api, db)
    response = await api.post(URL, json=await _manual_body(db, payment="account"), headers=headers)
    assert response.status_code == 422


async def test_account_belonging_to_another_customer_is_rejected(
    api: AsyncClient, db: AsyncSession
) -> None:
    other_customer = Customer(name="Luis", email="luis@example.com", phone="+52 624 000 0000")
    db.add(other_customer)
    await db.flush()
    account = ClientAccount(customer_id=other_customer.id, name="Luis's account")
    db.add(account)
    await db.flush()
    headers = await _login(api, db)

    body = await _manual_body(db, payment="account", account_id=str(account.id))
    response = await api.post(URL, json=body, headers=headers)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "account_not_found"


async def test_public_endpoint_rejects_manual_only_payment_methods(
    api: AsyncClient, db: AsyncSession
) -> None:
    body = await _manual_body(db, payment="stripe")
    body["type"] = "transfer"
    body["accepted_terms_version"] = "1"
    response = await api.post("/api/v1/bookings", json=body)
    assert response.status_code == 422


async def test_create_requires_csrf_header(api: AsyncClient, db: AsyncSession) -> None:
    await _login(api, db)
    response = await api.post(URL, json=await _manual_body(db))
    assert response.status_code == 403
