import hashlib
import hmac
import json
import time

import httpx
import pytest
import respx
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Booking, BookingStatus, EmailOutbox, Payment, PaymentProvider, PaymentStatus
from app.services.stripe_gateway import API_URL
from tests.test_admin_booking_actions import _login
from tests.test_admin_bookings import _create
from tests.test_bookings import _transfer

URL = "/api/v1/admin/bookings"
SECRET = "whsec_test"
CHECKOUT_ID = "cs_test_1"
CHECKOUT_URL = "https://checkout.stripe.com/pay/cs_test_1"


async def _booking_id(db: AsyncSession, code: str) -> str:
    booking_id = await db.scalar(select(Booking.id).where(Booking.code == code))
    assert booking_id is not None
    return str(booking_id)


def _checkout_session(*, status: str = "open", payment_status: str = "unpaid") -> dict:
    return {
        "id": CHECKOUT_ID,
        "url": CHECKOUT_URL,
        "status": status,
        "payment_status": payment_status,
    }


@respx.mock(base_url=API_URL)
async def test_generate_payment_link_calls_stripe_and_queues_email(
    api: AsyncClient, db: AsyncSession, respx_mock: respx.MockRouter
) -> None:
    created = await _create(api, db)
    booking_id = await _booking_id(db, created["code"])
    route = respx_mock.post("/checkout/sessions").mock(
        return_value=httpx.Response(200, json=_checkout_session())
    )
    headers = await _login(api, db)

    response = await api.post(f"{URL}/{booking_id}/payment-link", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["url"] == CHECKOUT_URL
    assert route.call_count == 1

    payment = await db.scalar(select(Payment).where(Payment.booking_id == booking_id))
    assert payment is not None
    assert payment.stripe_checkout_session_id == CHECKOUT_ID

    # Dos correos "pending_payment" en la misma transacción (mismo `now()`): el de crear la
    # reserva y este; se distinguen por el link que llevan, no por la fecha.
    emails = (
        await db.scalars(
            select(EmailOutbox).where(EmailOutbox.template == "booking_pending_payment")
        )
    ).all()
    assert any(e.context.get("manage_url") == CHECKOUT_URL for e in emails)


@respx.mock(base_url=API_URL)
async def test_calling_it_twice_reuses_the_open_session(
    api: AsyncClient, db: AsyncSession, respx_mock: respx.MockRouter
) -> None:
    created = await _create(api, db)
    booking_id = await _booking_id(db, created["code"])
    post = respx_mock.post("/checkout/sessions").mock(
        return_value=httpx.Response(200, json=_checkout_session())
    )
    get = respx_mock.get(f"/checkout/sessions/{CHECKOUT_ID}").mock(
        return_value=httpx.Response(200, json=_checkout_session())
    )
    headers = await _login(api, db)

    first = await api.post(f"{URL}/{booking_id}/payment-link", headers=headers)
    second = await api.post(f"{URL}/{booking_id}/payment-link", headers=headers)
    assert first.json()["url"] == second.json()["url"] == CHECKOUT_URL
    assert (post.call_count, get.call_count) == (1, 1)


async def test_cannot_generate_a_link_for_a_booking_that_is_not_pending(
    api: AsyncClient, db: AsyncSession
) -> None:
    body = await _transfer(db, payment="cash")
    created = (await api.post("/api/v1/bookings", json=body)).json()
    assert created["status"] == "confirmed"
    booking_id = await _booking_id(db, created["code"])
    headers = await _login(api, db)

    response = await api.post(f"{URL}/{booking_id}/payment-link", headers=headers)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "not_payable"


async def test_payment_link_requires_csrf_header(api: AsyncClient, db: AsyncSession) -> None:
    created = await _create(api, db)
    booking_id = await _booking_id(db, created["code"])
    await _login(api, db)

    response = await api.post(f"{URL}/{booking_id}/payment-link")
    assert response.status_code == 403


def _sign(payload: bytes, secret: str = SECRET) -> str:
    timestamp = int(time.time())
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256)
    return f"t={timestamp},v1={digest.hexdigest()}"


async def test_checkout_session_completed_webhook_marks_the_booking_paid(
    api: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    get_settings.cache_clear()

    created = await _create(api, db)
    booking_id = await _booking_id(db, created["code"])
    booking = await db.get(Booking, booking_id)
    assert booking is not None
    db.add(
        Payment(
            company_id=booking.company_id,
            booking_id=booking_id,
            provider=PaymentProvider.STRIPE,
            status=PaymentStatus.PENDING,
            amount_cents=created["total_cents"],
            currency=booking.currency,
            stripe_checkout_session_id=CHECKOUT_ID,
        )
    )
    await db.flush()

    event = {
        "id": "evt_1",
        "type": "checkout.session.completed",
        "data": {"object": _checkout_session(status="complete", payment_status="paid")},
    }
    payload = json.dumps(event).encode()
    response = await api.post(
        "/api/v1/webhooks/stripe",
        content=payload,
        headers={"Stripe-Signature": _sign(payload)},
    )
    assert response.status_code == 200, response.text

    await db.refresh(booking)
    assert booking.status == BookingStatus.PAID
