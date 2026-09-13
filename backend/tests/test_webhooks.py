import hashlib
import hmac
import json
import time

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Booking, BookingStatus, Payment, PaymentProvider, PaymentStatus, StripeEvent
from tests.test_booking_access import _book
from tests.test_bookings import URL, _transfer

SECRET = "whsec_test"
WEBHOOK = "/api/v1/webhooks/stripe"


@pytest.fixture(autouse=True)
def _configured_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    get_settings.cache_clear()


def _sign(payload: bytes, secret: str = SECRET) -> str:
    timestamp = int(time.time())
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256)
    return f"t={timestamp},v1={digest.hexdigest()}"


async def _post_event(api: AsyncClient, event: dict, *, signature: str | None = None) -> None:
    body = json.dumps(event).encode()
    headers = {"Stripe-Signature": signature or _sign(body)}
    response = await api.post(WEBHOOK, content=body, headers=headers)
    assert response.status_code == 200, response.text


def _event(kind: str, event_id: str, obj: dict) -> dict:
    return {"id": event_id, "type": kind, "data": {"object": obj}}


async def _pay(api: AsyncClient, db: AsyncSession, **changes: object) -> tuple[dict, Booking]:
    body = await _transfer(db, **changes)
    created = (await api.post(URL, json=body)).json()
    booking = await db.scalar(select(Booking).where(Booking.code == created["code"]))
    assert booking is not None
    db.add(
        Payment(
            company_id=booking.company_id,
            booking_id=booking.id,
            provider=PaymentProvider.STRIPE,
            status=PaymentStatus.PENDING,
            amount_cents=created["total_cents"],
            currency=booking.currency,
            stripe_payment_intent_id="pi_webhook_1",
        )
    )
    await db.flush()
    return created, booking


async def test_invalid_signature_is_rejected(api: AsyncClient) -> None:
    body = json.dumps({"id": "evt_1", "type": "payment_intent.succeeded"}).encode()
    response = await api.post(WEBHOOK, content=body, headers={"Stripe-Signature": "t=1,v1=bad"})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_signature"


async def test_payment_intent_succeeded_marks_the_booking_paid(
    api: AsyncClient, db: AsyncSession
) -> None:
    created, booking = await _pay(api, db)
    intent = {"id": "pi_webhook_1", "amount": created["total_cents"], "currency": "usd"}
    await _post_event(api, _event("payment_intent.succeeded", "evt_1", intent))

    await db.refresh(booking)
    payment = await db.scalar(select(Payment).where(Payment.booking_id == booking.id))
    assert payment is not None
    assert (booking.status.value, payment.status) == ("paid", PaymentStatus.SUCCEEDED)


async def test_same_event_id_is_only_processed_once(api: AsyncClient, db: AsyncSession) -> None:
    created, _booking = await _pay(api, db)
    intent = {"id": "pi_webhook_1", "amount": created["total_cents"], "currency": "usd"}
    event = _event("payment_intent.succeeded", "evt_repeat", intent)
    await _post_event(api, event)
    await _post_event(api, event)  # Sin esto, el segundo intento de pasar a PAID rompería.

    assert await db.scalar(select(StripeEvent).where(StripeEvent.id == "evt_repeat")) is not None
    events = (await db.scalars(select(StripeEvent))).all()
    assert len(events) == 1


async def test_cash_deposit_webhook_confirms_instead_of_paid(
    api: AsyncClient, db: AsyncSession
) -> None:
    created, booking = await _pay(api, db, vehicle_class="ESCALADE", payment="cash")
    assert created["status"] == "pending_payment"
    intent = {"id": "pi_webhook_1", "amount": 10000, "currency": "usd"}
    await _post_event(api, _event("payment_intent.succeeded", "evt_deposit", intent))
    await db.refresh(booking)
    assert booking.status.value == "confirmed"


async def test_webhook_does_not_redo_a_quick_confirmation_that_already_happened(
    api: AsyncClient, db: AsyncSession
) -> None:
    """El navegador ya confirmó (F4.3); el webhook llega después y no debe tocar nada."""
    created = await _book(api, db)
    booking = await db.scalar(select(Booking).where(Booking.code == created["code"]))
    assert booking is not None
    db.add(
        Payment(
            company_id=booking.company_id,
            booking_id=booking.id,
            provider=PaymentProvider.STRIPE,
            status=PaymentStatus.SUCCEEDED,
            amount_cents=created["total_cents"],
            currency=booking.currency,
            stripe_payment_intent_id="pi_already_done",
        )
    )
    booking.status = BookingStatus.PAID
    await db.flush()
    intent = {"id": "pi_already_done", "amount": created["total_cents"], "currency": "usd"}
    await _post_event(api, _event("payment_intent.succeeded", "evt_late", intent))
    await db.refresh(booking)
    assert booking.status.value == "paid"


async def test_payment_failed_marks_the_payment_without_touching_the_booking(
    api: AsyncClient, db: AsyncSession
) -> None:
    _created, booking = await _pay(api, db)
    await _post_event(
        api, _event("payment_intent.payment_failed", "evt_fail", {"id": "pi_webhook_1"})
    )
    await db.refresh(booking)
    payment = await db.scalar(select(Payment).where(Payment.booking_id == booking.id))
    assert payment is not None
    assert (booking.status.value, payment.status) == ("pending_payment", PaymentStatus.FAILED)


async def test_charge_refunded_updates_the_payment(api: AsyncClient, db: AsyncSession) -> None:
    created, booking = await _pay(api, db)
    charge = {"payment_intent": "pi_webhook_1", "amount_refunded": created["total_cents"]}
    await _post_event(api, _event("charge.refunded", "evt_refund", charge))
    payment = await db.scalar(select(Payment).where(Payment.booking_id == booking.id))
    assert payment is not None
    assert (payment.status, payment.refunded_cents) == (
        PaymentStatus.REFUNDED,
        created["total_cents"],
    )


async def test_unrecognized_event_type_is_stored_and_ignored(
    api: AsyncClient, db: AsyncSession
) -> None:
    await _post_event(api, _event("checkout.session.completed", "evt_checkout", {"id": "cs_1"}))
    assert await db.scalar(select(StripeEvent).where(StripeEvent.id == "evt_checkout")) is not None
