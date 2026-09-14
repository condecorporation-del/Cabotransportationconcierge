import uuid
from datetime import UTC, datetime

import httpx
import respx
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AdminRole,
    AuditLog,
    Booking,
    BookingSource,
    BookingStatus,
    BookingType,
    Customer,
    EmailOutbox,
    Payment,
    PaymentProvider,
    PaymentStatus,
)
from app.services.stripe_gateway import API_URL
from tests.test_admin_auth import PASSWORD, _admin, _csrf_headers
from tests.test_admin_auth import URL as AUTH_URL
from tests.test_admin_bookings import _create
from tests.test_bookings import _transfer

URL = "/api/v1/admin/bookings"
INTENT_ID = "pi_admin_action_1"


async def _login(
    api: AsyncClient, db: AsyncSession, role: AdminRole = AdminRole.DISPATCHER
) -> dict[str, str]:
    await _admin(db, role=role)
    response = await api.post(
        AUTH_URL + "/login", json={"email": "admin@example.com", "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return _csrf_headers(api)


async def _booking_id(db: AsyncSession, code: str) -> uuid.UUID:
    booking_id = await db.scalar(select(Booking.id).where(Booking.code == code))
    assert booking_id is not None
    return booking_id


async def _offline_hold(db: AsyncSession) -> Booking:
    customer = Customer(
        name="Ana López", email=f"{uuid.uuid4().hex}@example.com", phone="+52 624 111 2222"
    )
    db.add(customer)
    await db.flush()
    booking = Booking(
        code=f"CTC-2026-{uuid.uuid4().hex[:6].upper()}",
        status=BookingStatus.OFFLINE_HOLD,
        source=BookingSource.ADMIN,
        booking_type=BookingType.TRANSFER,
        customer_id=customer.id,
        subtotal_cents=10000,
        discount_cents=0,
        tax_cents=0,
        total_cents=10000,
    )
    db.add(booking)
    await db.flush()
    return booking


async def _pay_with_stripe(
    api: AsyncClient, db: AsyncSession, code: str, amount_cents: int
) -> None:
    booking_id = await _booking_id(db, code)
    company_id = await db.scalar(select(Booking.company_id).where(Booking.id == booking_id))
    db.add(
        Payment(
            company_id=company_id,
            booking_id=booking_id,
            provider=PaymentProvider.STRIPE,
            status=PaymentStatus.SUCCEEDED,
            amount_cents=amount_cents,
            currency="USD",
            stripe_payment_intent_id=INTENT_ID,
            paid_at=datetime.now(UTC),
        )
    )
    await db.flush()


async def test_confirm_moves_offline_hold_to_confirmed(api: AsyncClient, db: AsyncSession) -> None:
    booking = await _offline_hold(db)
    headers = await _login(api, db)
    response = await api.post(f"{URL}/{booking.id}/confirm", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "confirmed"


async def test_confirm_from_pending_payment_is_a_409(api: AsyncClient, db: AsyncSession) -> None:
    created = await _create(api, db)
    booking_id = await _booking_id(db, created["code"])
    headers = await _login(api, db)
    response = await api.post(f"{URL}/{booking_id}/confirm", headers=headers)
    assert response.status_code == 409


async def test_mark_paid_moves_pending_payment_to_paid(api: AsyncClient, db: AsyncSession) -> None:
    created = await _create(api, db)
    booking_id = await _booking_id(db, created["code"])
    headers = await _login(api, db)
    response = await api.post(
        f"{URL}/{booking_id}/mark-paid", json={"provider": "bank_transfer"}, headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "paid"
    [payment] = (await db.scalars(select(Payment).where(Payment.booking_id == booking_id))).all()
    assert (payment.provider, payment.status) == (
        PaymentProvider.BANK_TRANSFER,
        PaymentStatus.SUCCEEDED,
    )


async def test_mark_paid_on_a_cash_deposit_booking_confirms_directly(
    api: AsyncClient, db: AsyncSession
) -> None:
    body = await _transfer(db, vehicle_class="ESCALADE", payment="cash")
    created = (await api.post("/api/v1/bookings", json=body)).json()
    assert created["status"] == "pending_payment"
    booking_id = await _booking_id(db, created["code"])
    headers = await _login(api, db)

    response = await api.post(
        f"{URL}/{booking_id}/mark-paid", json={"provider": "cash"}, headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "confirmed"


async def test_mark_paid_when_not_pending_is_rejected(api: AsyncClient, db: AsyncSession) -> None:
    booking = await _offline_hold(db)
    headers = await _login(api, db)
    response = await api.post(
        f"{URL}/{booking.id}/mark-paid", json={"provider": "cash"}, headers=headers
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "not_payable"


async def test_mark_unpaid_reverts_a_manual_payment(api: AsyncClient, db: AsyncSession) -> None:
    created = await _create(api, db)
    booking_id = await _booking_id(db, created["code"])
    headers = await _login(api, db)
    await api.post(f"{URL}/{booking_id}/mark-paid", json={"provider": "cash"}, headers=headers)

    response = await api.post(f"{URL}/{booking_id}/mark-unpaid", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "pending_payment"
    [payment] = (await db.scalars(select(Payment).where(Payment.booking_id == booking_id))).all()
    assert payment.status is PaymentStatus.CANCELLED


async def test_mark_unpaid_rejects_a_stripe_payment(api: AsyncClient, db: AsyncSession) -> None:
    created = await _create(api, db)
    await _pay_with_stripe(api, db, created["code"], created["total_cents"])
    booking_id = await _booking_id(db, created["code"])
    booking = await db.get(Booking, booking_id)
    assert booking is not None
    booking.status = BookingStatus.PAID
    await db.flush()
    headers = await _login(api, db)

    response = await api.post(f"{URL}/{booking_id}/mark-unpaid", headers=headers)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "manual_payment_required"


async def test_cancel_without_refund(api: AsyncClient, db: AsyncSession) -> None:
    created = await _create(api, db)
    booking_id = await _booking_id(db, created["code"])
    headers = await _login(api, db)
    response = await api.post(
        f"{URL}/{booking_id}/cancel", json={"reason": "Client asked by phone"}, headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"


@respx.mock(base_url=API_URL)
async def test_cancel_with_refund_calls_stripe(
    api: AsyncClient, db: AsyncSession, respx_mock: respx.MockRouter
) -> None:
    created = await _create(api, db)
    await _pay_with_stripe(api, db, created["code"], created["total_cents"])
    refund = respx_mock.post("/refunds").mock(
        return_value=httpx.Response(200, json={"id": "re_1", "amount": created["total_cents"]})
    )
    booking_id = await _booking_id(db, created["code"])
    headers = await _login(api, db)

    response = await api.post(f"{URL}/{booking_id}/cancel", json={"refund": True}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "cancelled"
    assert refund.call_count == 1
    [payment] = (await db.scalars(select(Payment).where(Payment.booking_id == booking_id))).all()
    assert payment.status is PaymentStatus.REFUNDED


async def test_cancel_with_refund_but_no_stripe_payment_is_rejected(
    api: AsyncClient, db: AsyncSession
) -> None:
    created = await _create(api, db)
    booking_id = await _booking_id(db, created["code"])
    headers = await _login(api, db)
    await api.post(f"{URL}/{booking_id}/mark-paid", json={"provider": "cash"}, headers=headers)

    response = await api.post(f"{URL}/{booking_id}/cancel", json={"refund": True}, headers=headers)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "manual_refund_required"


async def test_resend_confirmation_queues_the_email_again(
    api: AsyncClient, db: AsyncSession
) -> None:
    created = await _create(api, db)
    booking_id = await _booking_id(db, created["code"])
    headers = await _login(api, db)

    response = await api.post(f"{URL}/{booking_id}/resend-confirmation", headers=headers)
    assert response.status_code == 204, response.text
    emails = (
        await db.scalars(
            select(EmailOutbox).where(
                EmailOutbox.booking_id == booking_id,
                EmailOutbox.template == "booking_pending_payment",
            )
        )
    ).all()
    # Uno al crear la reserva y otro al reenviar (F6.5).
    assert len(emails) == 2


async def test_delete_hides_the_booking_from_listing_and_detail(
    api: AsyncClient, db: AsyncSession
) -> None:
    created = await _create(api, db)
    booking_id = await _booking_id(db, created["code"])
    headers = await _login(api, db)

    response = await api.delete(f"{URL}/{booking_id}", headers=headers)
    assert response.status_code == 204, response.text

    assert (await api.get(f"{URL}/{booking_id}")).status_code == 404
    listing = await api.get(URL)
    assert created["code"] not in [item["code"] for item in listing.json()["items"]]


async def test_mutation_without_csrf_header_is_rejected(api: AsyncClient, db: AsyncSession) -> None:
    created = await _create(api, db)
    booking_id = await _booking_id(db, created["code"])
    await _login(api, db)

    response = await api.post(f"{URL}/{booking_id}/confirm")
    assert response.status_code == 403


async def test_viewer_role_cannot_cancel_a_booking(api: AsyncClient, db: AsyncSession) -> None:
    created = await _create(api, db)
    booking_id = await _booking_id(db, created["code"])
    headers = await _login(api, db, role=AdminRole.VIEWER)

    response = await api.post(f"{URL}/{booking_id}/cancel", json={}, headers=headers)
    assert response.status_code == 403


async def test_timeline_records_the_admin_who_confirmed_it(
    api: AsyncClient, db: AsyncSession
) -> None:
    booking = await _offline_hold(db)
    headers = await _login(api, db)
    await api.post(f"{URL}/{booking.id}/confirm", headers=headers)

    response = await api.get(f"{URL}/{booking.id}/timeline")
    assert response.status_code == 200, response.text
    [entry] = response.json()
    assert entry["actor"] == "admin"
    assert entry["admin_user_id"] is not None
    assert entry["after"]["status"] == "confirmed"

    [log] = (await db.scalars(select(AuditLog).where(AuditLog.entity_id == booking.id))).all()
    assert log.admin_user_id is not None
