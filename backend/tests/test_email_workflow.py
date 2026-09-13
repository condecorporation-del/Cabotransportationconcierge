"""F5.2, F5.4-F5.6, F5.10: qué se encola y a quién, en cada evento real de una reserva."""

import pytest
import respx
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import (
    Booking,
    CompanySettings,
    EmailOutbox,
    Payment,
    PaymentProvider,
    PaymentStatus,
)
from app.services.stripe_gateway import API_URL
from app.templates.emails import TEMPLATES, render
from tests.test_booking_access import _bearer, _book
from tests.test_bookings import URL, _transfer

OPS = "ops@example.com"


@pytest.fixture(autouse=True)
def _ops_inbox(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_OPS_TO", OPS)
    get_settings.cache_clear()


async def _templates_for(db: AsyncSession, recipient: str) -> list[str]:
    rows = await db.scalars(select(EmailOutbox).order_by(EmailOutbox.created_at))
    return [row.template for row in rows if recipient in row.to_addresses]


@pytest.mark.parametrize("language", ["en", "es"])
def test_every_template_renders_in_both_languages(language: str) -> None:
    context = {
        "code": "CTC-2026-000123",
        "manage_url": "https://example.com/my-trip",
        "voucher_url": "https://example.com/voucher.pdf",
        "balance_note": "Balance due on arrival: $100.00 USD",
        "customer_name": "Ana López",
        "total_display": "$265.00 USD",
        "payment_method": "card",
        "status": "paid",
        "reason": "Flight cancelled",
        "name": "Ana López",
        "email": "ana@example.com",
        "message": "Do you have car seats?",
    }
    for template in TEMPLATES:
        subject, html, text = render(template, language, context)
        assert subject
        assert html.startswith("<!doctype html")
        assert text


async def test_booking_with_card_queues_pending_payment_and_ops(
    api: AsyncClient, db: AsyncSession
) -> None:
    created = (await api.post(URL, json=await _transfer(db, payment="card"))).json()
    assert await _templates_for(db, "ana@example.com") == ["booking_pending_payment"]
    assert await _templates_for(db, OPS) == ["booking_new"]
    row = await db.scalar(select(EmailOutbox).where(EmailOutbox.template == "booking_new"))
    booking_id = await db.scalar(select(Booking.id).where(Booking.code == created["code"]))
    assert row is not None
    assert (row.context["payment_method"], row.booking_id) == ("card", booking_id)


async def test_cash_no_deposit_booking_queues_confirmation_right_away(
    api: AsyncClient, db: AsyncSession
) -> None:
    await api.post(URL, json=await _transfer(db, payment="cash"))
    assert await _templates_for(db, "ana@example.com") == ["booking_confirmed"]
    context = (
        await db.scalar(select(EmailOutbox).where(EmailOutbox.template == "booking_confirmed"))
    ).context
    assert context["balance_note"] is None


async def test_confirming_payment_queues_confirmation_and_ops_notice(
    api: AsyncClient, db: AsyncSession
) -> None:
    created = await _book(api, db)
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
            stripe_payment_intent_id="pi_email_test",
        )
    )
    await db.flush()
    with respx.mock(base_url=API_URL) as mock:
        mock.get("/payment_intents/pi_email_test").respond(
            200,
            json={
                "id": "pi_email_test",
                "amount": created["total_cents"],
                "currency": booking.currency.lower(),
                "status": "succeeded",
                "metadata": {"booking_id": str(booking.id), "company_id": str(booking.company_id)},
            },
        )
        response = await api.post(
            f"{URL}/{created['code']}/payments/confirm",
            json={"payment_intent_id": "pi_email_test"},
            headers=_bearer(created["token"]),
        )
    assert response.status_code == 200, response.text
    assert await _templates_for(db, "ana@example.com") == [
        "booking_pending_payment",
        "booking_confirmed",
    ]
    assert await _templates_for(db, OPS) == ["booking_new", "booking_paid_ops"]


async def test_change_and_cancel_each_queue_customer_and_ops_emails(
    api: AsyncClient, db: AsyncSession
) -> None:
    created = await _book(api, db)
    await db.execute(update(CompanySettings).values(change_hours=0, cancellation_hours=0))
    headers = _bearer(created["token"])
    url = f"{URL}/{created['code']}"

    await api.patch(url, json={"notes": "Two surfboards"}, headers=headers)
    assert await _templates_for(db, "ana@example.com") == [
        "booking_pending_payment",
        "booking_changed",
    ]
    assert await _templates_for(db, OPS) == ["booking_new", "booking_changed_ops"]

    await api.post(f"{url}/cancel", json={"reason": "Trip postponed"}, headers=headers)
    assert await _templates_for(db, "ana@example.com") == [
        "booking_pending_payment",
        "booking_changed",
        "booking_cancelled",
    ]
    cancel_row = await db.scalar(
        select(EmailOutbox).where(EmailOutbox.template == "booking_cancelled_ops")
    )
    assert cancel_row is not None
    assert cancel_row.context["reason"] == "Trip postponed"


async def test_contact_form_queues_ack_and_lead(api: AsyncClient, db: AsyncSession) -> None:
    body = {"name": "Ana López", "email": "ana@example.com", "message": "Do you have car seats?"}
    response = await api.post("/api/v1/contact", json=body)
    assert response.status_code == 202, response.text
    assert await _templates_for(db, "ana@example.com") == ["contact_ack"]
    assert await _templates_for(db, OPS) == ["contact_lead"]


async def test_without_email_ops_to_configured_only_the_customer_is_queued(
    api: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("EMAIL_OPS_TO", raising=False)
    get_settings.cache_clear()
    await api.post(URL, json=await _transfer(db))
    rows = (await db.scalars(select(EmailOutbox))).all()
    assert [row.template for row in rows] == ["booking_pending_payment"]
