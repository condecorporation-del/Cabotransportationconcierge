"""Pago de una reserva con Stripe (F4.2, F4.3): el monto siempre sale de la reserva ya creada.

`stripe_gateway.py` es el único que habla con Stripe; aquí solo se decide qué cobrar y se
guarda el resultado. El webhook (F4.4) es la fuente de verdad final; esto confirma al instante.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import (
    AuditActor,
    Booking,
    BookingStatus,
    Company,
    Payment,
    PaymentProvider,
    PaymentStatus,
)
from app.services.booking_state import transition
from app.services.stripe_gateway import StripeGateway


class PaymentError(AppError):
    status_code = 400


def _amount(booking: Booking) -> int:
    """Con efectivo solo se cobra el depósito (vehículos premium); con tarjeta, todo."""
    return booking.deposit_cents if booking.payment_method == "cash" else booking.total_cents


async def create_or_reuse_intent(
    session: AsyncSession, booking: Booking, company: Company, gateway: StripeGateway
) -> str:
    """Devuelve el `client_secret` del Payment Element; dos llamadas dan el mismo."""
    if booking.status is not BookingStatus.PENDING_PAYMENT:
        raise PaymentError("not_payable", "This booking is not waiting for a payment.")
    amount = _amount(booking)
    existing = await session.scalar(
        select(Payment).where(
            Payment.booking_id == booking.id, Payment.status == PaymentStatus.PENDING
        )
    )
    if existing and existing.stripe_payment_intent_id:
        intent = await gateway.retrieve_payment_intent(existing.stripe_payment_intent_id)
    else:
        intent = await gateway.create_payment_intent(
            amount_cents=amount,
            currency=booking.currency,
            metadata={"booking_id": str(booking.id), "company_id": str(company.id)},
            # Misma clave para reintentos del cliente: Stripe devuelve el mismo intent.
            idempotency_key=f"booking-intent:{booking.id}",
        )
        session.add(
            Payment(
                booking_id=booking.id,
                provider=PaymentProvider.STRIPE,
                status=PaymentStatus.PENDING,
                amount_cents=amount,
                currency=booking.currency,
                stripe_payment_intent_id=intent["id"],
            )
        )
        await session.flush()
    return str(intent["client_secret"])


async def confirm_payment(
    session: AsyncSession,
    booking: Booking,
    company: Company,
    payment_intent_id: str,
    gateway: StripeGateway,
    ip: str | None,
) -> None:
    """Confirmación rápida desde el navegador; valida contra Stripe antes de marcar pagado."""
    if booking.status is not BookingStatus.PENDING_PAYMENT:
        raise PaymentError("not_payable", "This booking is not waiting for a payment.")
    payment = await session.scalar(
        select(Payment).where(
            Payment.booking_id == booking.id, Payment.stripe_payment_intent_id == payment_intent_id
        )
    )
    if payment is None:
        raise PaymentError("payment_mismatch", "This payment does not belong to this booking.")

    intent = await gateway.retrieve_payment_intent(payment_intent_id)
    metadata = intent.get("metadata") or {}
    valid = (
        metadata.get("booking_id") == str(booking.id)
        and metadata.get("company_id") == str(company.id)
        and int(intent.get("amount", -1)) == payment.amount_cents
        and str(intent.get("currency", "")).upper() == booking.currency
    )
    if not valid:
        raise PaymentError("payment_mismatch", "This payment does not belong to this booking.")
    if intent.get("status") != "succeeded":
        raise PaymentError("payment_not_completed", "The payment has not completed yet.")

    payment.status = PaymentStatus.SUCCEEDED
    payment.paid_at = datetime.now(UTC)
    transition(session, booking, BookingStatus.PAID, actor=AuditActor.CUSTOMER, ip=ip)
    if booking.payment_method == "cash":
        # El depósito confirma la reserva; el saldo lo cobra el chofer (§8.2: PAID -> CONFIRMED).
        transition(session, booking, BookingStatus.CONFIRMED, actor=AuditActor.SYSTEM, ip=ip)
