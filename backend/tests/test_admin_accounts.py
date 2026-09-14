from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, Customer
from tests.test_admin_booking_actions import _login
from tests.test_admin_bookings import _create

URL = "/api/v1/admin/accounts"


async def _customer(db: AsyncSession, email: str = "ana@example.com") -> Customer:
    customer = Customer(name="Ana López", email=email, phone="+52 624 111 2222")
    db.add(customer)
    await db.flush()
    return customer


async def test_create_account_and_charge_it(api: AsyncClient, db: AsyncSession) -> None:
    customer = await _customer(db)
    headers = await _login(api, db)

    created = await api.post(
        URL, json={"customer_id": str(customer.id), "name": "Ana's account"}, headers=headers
    )
    assert created.status_code == 201, created.text
    account_id = created.json()["id"]

    charge = await api.post(
        f"{URL}/{account_id}/charges",
        json={"description": "Airport transfer", "amount_cents": 5000},
        headers=headers,
    )
    assert charge.status_code == 201, charge.text

    detail = (await api.get(f"{URL}/{account_id}", headers=headers)).json()
    assert detail["balance_cents"] == 5000
    assert len(detail["charges"]) == 1


async def test_payment_reduces_the_balance(api: AsyncClient, db: AsyncSession) -> None:
    customer = await _customer(db)
    headers = await _login(api, db)
    account_id = (
        await api.post(
            URL, json={"customer_id": str(customer.id), "name": "Ana's account"}, headers=headers
        )
    ).json()["id"]
    await api.post(
        f"{URL}/{account_id}/charges",
        json={"description": "Airport transfer", "amount_cents": 5000},
        headers=headers,
    )

    payment = await api.post(
        f"{URL}/{account_id}/payments",
        json={"method": "cash", "amount_cents": 2000},
        headers=headers,
    )
    assert payment.status_code == 201, payment.text

    detail = (await api.get(f"{URL}/{account_id}", headers=headers)).json()
    assert detail["balance_cents"] == 3000
    assert len(detail["payments"]) == 1


async def test_voiding_a_charge_removes_it_from_the_balance(
    api: AsyncClient, db: AsyncSession
) -> None:
    customer = await _customer(db)
    headers = await _login(api, db)
    account_id = (
        await api.post(
            URL, json={"customer_id": str(customer.id), "name": "Ana's account"}, headers=headers
        )
    ).json()["id"]
    charge_id = (
        await api.post(
            f"{URL}/{account_id}/charges",
            json={"description": "Airport transfer", "amount_cents": 5000},
            headers=headers,
        )
    ).json()["id"]

    voided = await api.patch(
        f"{URL}/{account_id}/charges/{charge_id}", json={"status": "void"}, headers=headers
    )
    assert voided.status_code == 200, voided.text

    detail = (await api.get(f"{URL}/{account_id}", headers=headers)).json()
    assert detail["balance_cents"] == 0


async def test_linking_an_existing_booking_charges_its_total(
    api: AsyncClient, db: AsyncSession
) -> None:
    created = await _create(api, db)
    customer = await db.scalar(select(Customer).where(Customer.email == "ana@example.com"))
    assert customer is not None
    booking_id = await db.scalar(select(Booking.id).where(Booking.code == created["code"]))
    headers = await _login(api, db)
    account_id = (
        await api.post(
            URL, json={"customer_id": str(customer.id), "name": "Ana's account"}, headers=headers
        )
    ).json()["id"]

    linked = await api.post(
        f"{URL}/{account_id}/bookings", json={"booking_id": str(booking_id)}, headers=headers
    )
    assert linked.status_code == 201, linked.text

    detail = (await api.get(f"{URL}/{account_id}", headers=headers)).json()
    assert detail["balance_cents"] == created["total_cents"]

    again = await api.post(
        f"{URL}/{account_id}/bookings", json={"booking_id": str(booking_id)}, headers=headers
    )
    assert again.status_code == 422
    assert again.json()["detail"]["code"] == "already_charged"


async def test_linking_a_booking_that_belongs_to_another_customer_is_rejected(
    api: AsyncClient, db: AsyncSession
) -> None:
    other_customer = await _customer(db, email="other@example.com")
    created = await _create(api, db)  # dueño real: ana@example.com
    booking_id = await db.scalar(select(Booking.id).where(Booking.code == created["code"]))
    headers = await _login(api, db)
    account_id = (
        await api.post(
            URL,
            json={"customer_id": str(other_customer.id), "name": "Other's account"},
            headers=headers,
        )
    ).json()["id"]

    response = await api.post(
        f"{URL}/{account_id}/bookings", json={"booking_id": str(booking_id)}, headers=headers
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "booking_not_found"
