import json
from urllib.parse import parse_qs

import httpx
import respx
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, CompanySettings, Payment, PaymentProvider, PaymentStatus
from app.services.stripe_gateway import API_URL
from tests.test_booking_access import _bearer, _book
from tests.test_bookings import URL, _transfer

INTENT_ID = "pi_test_1"


def _created(booking_id: str, company_id: str, *, status: str = "requires_payment_method") -> dict:
    return {
        "id": INTENT_ID,
        "client_secret": f"{INTENT_ID}_secret",
        "status": status,
        "metadata": {"booking_id": booking_id, "company_id": company_id},
    }


def _handler(booking_id: str, company_id: str, *, status: str = "requires_payment_method"):
    def respond(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            form = parse_qs(request.content.decode())
            amount, currency = int(form["amount"][0]), form["currency"][0]
        else:
            amount, currency = None, None
        body = _created(booking_id, company_id, status=status)
        if amount is not None:
            body |= {"amount": amount, "currency": currency}
        return httpx.Response(200, content=json.dumps(body))

    return respond


async def _add_payment(db: AsyncSession, booking: Booking, intent_id: str, amount: int) -> None:
    db.add(
        Payment(
            company_id=booking.company_id,
            booking_id=booking.id,
            provider=PaymentProvider.STRIPE,
            status=PaymentStatus.PENDING,
            amount_cents=amount,
            currency=booking.currency,
            stripe_payment_intent_id=intent_id,
        )
    )
    await db.flush()


@respx.mock(base_url=API_URL)
async def test_intent_is_reused_without_creating_a_second_one(
    api: AsyncClient, db: AsyncSession, respx_mock: respx.MockRouter
) -> None:
    created = await _book(api, db)
    booking = await db.scalar(select(Booking).where(Booking.code == created["code"]))
    assert booking is not None
    handler = _handler(str(booking.id), str(booking.company_id))
    post = respx_mock.post("/payment_intents").mock(side_effect=handler)
    get = respx_mock.get(f"/payment_intents/{INTENT_ID}").mock(side_effect=handler)
    url, headers = f"{URL}/{created['code']}/payments/intent", _bearer(created["token"])

    first = await api.post(url, headers=headers)
    second = await api.post(url, headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() == {"client_secret": f"{INTENT_ID}_secret"}
    assert (post.call_count, get.call_count) == (1, 1)
    [payment] = (await db.scalars(select(Payment))).all()
    assert (payment.status, payment.stripe_payment_intent_id) == (PaymentStatus.PENDING, INTENT_ID)


@respx.mock(base_url=API_URL)
async def test_intent_amount_is_the_deposit_for_cash_premium_vehicles(
    api: AsyncClient, db: AsyncSession, respx_mock: respx.MockRouter
) -> None:
    body = await _transfer(db, vehicle_class="ESCALADE", payment="cash")
    created = (await api.post(URL, json=body)).json()
    assert created["status"] == "pending_payment"  # Escalade lleva depósito
    booking = await db.scalar(select(Booking).where(Booking.code == created["code"]))
    assert booking is not None
    route = respx_mock.post("/payment_intents").mock(
        side_effect=_handler(str(booking.id), str(booking.company_id))
    )
    response = await api.post(
        f"{URL}/{created['code']}/payments/intent", headers=_bearer(created["token"])
    )
    assert response.status_code == 200, response.text
    sent = parse_qs(route.calls.last.request.content.decode())
    assert int(sent["amount"][0]) == 10000 < created["total_cents"]


@respx.mock(base_url=API_URL)
async def test_confirm_marks_the_booking_paid_and_cannot_run_twice(
    api: AsyncClient, db: AsyncSession, respx_mock: respx.MockRouter
) -> None:
    created = await _book(api, db)
    booking = await db.scalar(select(Booking).where(Booking.code == created["code"]))
    assert booking is not None
    await _add_payment(db, booking, INTENT_ID, created["total_cents"])
    respx_mock.get(f"/payment_intents/{INTENT_ID}").mock(
        return_value=httpx.Response(
            200,
            json=_created(str(booking.id), str(booking.company_id), status="succeeded")
            | {"amount": created["total_cents"], "currency": booking.currency.lower()},
        )
    )
    headers = _bearer(created["token"])
    response = await api.post(
        f"{URL}/{created['code']}/payments/confirm",
        json={"payment_intent_id": INTENT_ID},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "paid"

    again = await api.post(
        f"{URL}/{created['code']}/payments/confirm",
        json={"payment_intent_id": INTENT_ID},
        headers=headers,
    )
    assert again.status_code == 400
    assert again.json()["detail"]["code"] == "not_payable"


@respx.mock(base_url=API_URL)
async def test_cash_deposit_confirmation_confirms_instead_of_paid(
    api: AsyncClient, db: AsyncSession, respx_mock: respx.MockRouter
) -> None:
    body = await _transfer(db, vehicle_class="ESCALADE", payment="cash")
    created = (await api.post(URL, json=body)).json()
    booking = await db.scalar(select(Booking).where(Booking.code == created["code"]))
    assert booking is not None
    await _add_payment(db, booking, "pi_deposit", 10000)
    respx_mock.get("/payment_intents/pi_deposit").mock(
        return_value=httpx.Response(
            200,
            json=_created(str(booking.id), str(booking.company_id), status="succeeded")
            | {"id": "pi_deposit", "amount": 10000, "currency": booking.currency.lower()},
        )
    )
    response = await api.post(
        f"{URL}/{created['code']}/payments/confirm",
        json={"payment_intent_id": "pi_deposit"},
        headers=_bearer(created["token"]),
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "confirmed"


async def test_confirming_with_another_bookings_intent_is_rejected(
    api: AsyncClient, db: AsyncSession
) -> None:
    first = await _book(api, db)
    second = await _book(api, db, email="luis@example.com")
    first_booking = await db.scalar(select(Booking).where(Booking.code == first["code"]))
    assert first_booking is not None
    await _add_payment(db, first_booking, "pi_of_first", first["total_cents"])
    response = await api.post(
        f"{URL}/{second['code']}/payments/confirm",
        json={"payment_intent_id": "pi_of_first"},
        headers=_bearer(second["token"]),
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "payment_mismatch"


async def test_cannot_pay_a_booking_that_is_not_pending(api: AsyncClient, db: AsyncSession) -> None:
    created = await _book(api, db)
    await db.execute(update(CompanySettings).values(cancellation_hours=0))
    await api.post(f"{URL}/{created['code']}/cancel", json={}, headers=_bearer(created["token"]))
    response = await api.post(
        f"{URL}/{created['code']}/payments/intent", headers=_bearer(created["token"])
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "not_payable"
