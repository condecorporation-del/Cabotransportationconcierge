import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AccountCharge,
    Booking,
    BookingSource,
    BookingStatus,
    BookingType,
    ClientAccount,
    Company,
    Customer,
    Payment,
    PaymentProvider,
    PaymentStatus,
    StripeEvent,
    VehicleClass,
    Zone,
)

Catalog = tuple[Company, Zone, VehicleClass]


@pytest.fixture
async def booking(db: AsyncSession, catalog: Catalog) -> Booking:
    customer = Customer(name="Ana", email="ana@example.com")
    db.add(customer)
    await db.flush()
    booking = Booking(
        code="CTC-2026-000010",
        status=BookingStatus.PENDING_PAYMENT,
        source=BookingSource.WEBSITE,
        booking_type=BookingType.TRANSFER,
        customer_id=customer.id,
        subtotal_cents=11000,
        total_cents=11000,
    )
    db.add(booking)
    await db.flush()
    return booking


def _stripe_payment(booking: Booking, intent: str, **amounts: int) -> Payment:
    return Payment(
        booking_id=booking.id,
        provider=PaymentProvider.STRIPE,
        status=PaymentStatus.SUCCEEDED,
        stripe_payment_intent_id=intent,
        amount_cents=amounts.get("amount_cents", 11000),
        refunded_cents=amounts.get("refunded_cents", 0),
    )


async def test_payment_intent_creates_a_single_payment(db: AsyncSession, booking: Booking) -> None:
    db.add_all([_stripe_payment(booking, "pi_123"), _stripe_payment(booking, "pi_123")])
    with pytest.raises(IntegrityError, match="uq_payments_stripe_payment_intent_id"):
        await db.flush()


async def test_refund_cannot_exceed_payment(db: AsyncSession, booking: Booking) -> None:
    db.add(_stripe_payment(booking, "pi_456", refunded_cents=11001))
    with pytest.raises(IntegrityError, match="ck_payments_amounts"):
        await db.flush()


async def test_stripe_event_is_processed_once(db: AsyncSession) -> None:
    db.add(StripeEvent(id="evt_1", type="payment_intent.succeeded", payload={}))
    await db.flush()
    db.expunge_all()
    db.add(StripeEvent(id="evt_1", type="payment_intent.succeeded", payload={}))
    with pytest.raises(IntegrityError, match="pk_stripe_events"):
        await db.flush()


async def test_account_charge_must_be_positive(db: AsyncSession, booking: Booking) -> None:
    account = ClientAccount(customer_id=booking.customer_id, name="Villa Sera")
    db.add(account)
    await db.flush()
    db.add(AccountCharge(account_id=account.id, description="Dinner run", amount_cents=0))
    with pytest.raises(IntegrityError, match="ck_account_charges_amount_positive"):
        await db.flush()


async def test_booking_with_payments_cannot_be_deleted(db: AsyncSession, booking: Booking) -> None:
    db.add(_stripe_payment(booking, f"pi_{uuid.uuid4().hex[:8]}"))
    await db.flush()
    await db.delete(booking)
    with pytest.raises(IntegrityError, match="fk_payments_booking_id_bookings"):
        await db.flush()
