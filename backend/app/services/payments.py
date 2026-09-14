"""Pago de una reserva con Stripe (F4.2 a F4.4): el monto siempre sale de la reserva ya creada.

`stripe_gateway.py` es el único que habla con Stripe; aquí solo se decide qué cobrar y se
guarda el resultado. El webhook es la fuente de verdad si la confirmación rápida del
navegador no llega a correr (se cerró la pestaña, se cayó la red); ambos caminos marcan
pagado por el mismo `settle_payment`, así que llegar por los dos no lo hace dos veces.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import booking_manage_url
from app.models import (
    AuditActor,
    Booking,
    BookingStatus,
    Company,
    Customer,
    Payment,
    PaymentProvider,
    PaymentStatus,
)
from app.services.booking_state import transition
from app.services.email import enqueue
from app.services.stripe_gateway import StripeGateway


class PaymentError(AppError):
    status_code = 400


async def settle_payment(
    session: AsyncSession,
    payment: Payment,
    booking: Booking,
    actor: AuditActor,
    ip: str | None,
    admin_user_id: uuid.UUID | None = None,
) -> None:
    """Único lugar que marca un pago exitoso: lo usan Stripe (confirmación y webhook) y F6.5."""
    payment.status = PaymentStatus.SUCCEEDED
    payment.paid_at = datetime.now(UTC)
    transition(
        session, booking, BookingStatus.PAID, actor=actor, admin_user_id=admin_user_id, ip=ip
    )
    if booking.payment_method == "cash":
        # El depósito confirma la reserva; el saldo lo cobra el chofer (§8.2: PAID -> CONFIRMED).
        transition(session, booking, BookingStatus.CONFIRMED, actor=AuditActor.SYSTEM, ip=ip)
    await notify_confirmation(session, booking)


async def notify_confirmation(session: AsyncSession, booking: Booking) -> None:
    """F5.4, F5.5: mismo correo de confirmación tanto si el pago fue completo como depósito."""
    customer = await session.get(Customer, booking.customer_id)
    if customer is None:
        return
    settings = get_settings()
    manage_url = booking_manage_url(booking.company_id, booking.code)
    balance = None
    if booking.payment_method == "cash":
        balance = f"Balance due on arrival: ${booking.total_cents / 100:,.2f} {booking.currency}"
    await enqueue(
        session,
        booking.company_id,
        "booking_confirmed",
        [customer.email],
        {
            "code": booking.code,
            "manage_url": manage_url,
            "voucher_url": manage_url,
            "balance_note": balance,
        },
        booking.language,
        booking.id,
    )
    if settings.email_ops_to:
        await enqueue(
            session,
            booking.company_id,
            "booking_paid_ops",
            [settings.email_ops_to],
            {"code": booking.code, "status": booking.status.value},
            booking_id=booking.id,
        )


def amount_due(booking: Booking) -> int:
    """Con efectivo solo se cobra el depósito (vehículos premium); con tarjeta, todo."""
    return booking.deposit_cents if booking.payment_method == "cash" else booking.total_cents


async def create_or_reuse_intent(
    session: AsyncSession, booking: Booking, company: Company, gateway: StripeGateway
) -> str:
    """Devuelve el `client_secret` del Payment Element; dos llamadas dan el mismo."""
    if booking.status is not BookingStatus.PENDING_PAYMENT:
        raise PaymentError("not_payable", "This booking is not waiting for a payment.")
    amount = amount_due(booking)
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


async def create_payment_link(
    session: AsyncSession, booking: Booking, company: Company, gateway: StripeGateway
) -> str:
    """F4.6: link real de Stripe Checkout (24 h) para una reserva pendiente de pago.

    A diferencia del Payment Element (F4.2), el cliente paga en la página de Stripe, no en la
    nuestra: la confirmación llega solo por el webhook (`checkout.session.completed`), no hay
    una "confirmación rápida" del navegador que la adelante.
    """
    if booking.status is not BookingStatus.PENDING_PAYMENT:
        raise PaymentError("not_payable", "This booking is not waiting for a payment.")
    amount = amount_due(booking)
    existing = await session.scalar(
        select(Payment).where(
            Payment.booking_id == booking.id,
            Payment.status == PaymentStatus.PENDING,
            Payment.stripe_checkout_session_id.is_not(None),
        )
    )
    if existing and existing.stripe_checkout_session_id:
        checkout = await gateway.retrieve_checkout_session(existing.stripe_checkout_session_id)
        if checkout.get("status") == "open":
            return str(checkout["url"])

    manage_url = booking_manage_url(booking.company_id, booking.code)
    checkout = await gateway.create_checkout_session(
        amount_cents=amount,
        currency=booking.currency,
        description=f"Booking {booking.code}",
        success_url=manage_url,
        cancel_url=manage_url,
        expires_at=int((datetime.now(UTC) + timedelta(hours=24)).timestamp()),
        metadata={"booking_id": str(booking.id), "company_id": str(company.id)},
        # Único por llamada: reintentos rápidos ya se resuelven arriba reusando la sesión abierta.
        idempotency_key=f"booking-checkout:{booking.id}:{uuid.uuid4()}",
    )
    if existing is not None:
        existing.stripe_checkout_session_id = checkout["id"]
        existing.amount_cents = amount
    else:
        session.add(
            Payment(
                booking_id=booking.id,
                provider=PaymentProvider.STRIPE,
                status=PaymentStatus.PENDING,
                amount_cents=amount,
                currency=booking.currency,
                stripe_checkout_session_id=checkout["id"],
            )
        )
    await session.flush()

    customer = await session.get(Customer, booking.customer_id)
    if customer is not None:
        await enqueue(
            session,
            booking.company_id,
            "booking_pending_payment",
            [customer.email],
            {"code": booking.code, "manage_url": str(checkout["url"])},
            booking.language,
            booking.id,
        )
    return str(checkout["url"])


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
    await settle_payment(session, payment, booking, AuditActor.CUSTOMER, ip)


async def handle_stripe_event(session: AsyncSession, event: dict[str, Any]) -> None:
    """F4.4: procesa lo que ya cambió en Stripe; `stripe_events` afuera evita repetirlo."""
    kind = event.get("type")
    data: dict[str, Any] = ((event.get("data") or {}).get("object")) or {}
    if kind == "payment_intent.succeeded":
        await _apply_success(session, data)
    elif kind == "payment_intent.payment_failed":
        await _apply_failure(session, data)
    elif kind == "charge.refunded":
        await _apply_refund(session, data)
    elif kind == "checkout.session.completed":
        await _apply_checkout_completed(session, data)


async def _payment_for(session: AsyncSession, intent_id: str | None) -> Payment | None:
    if not intent_id:
        return None
    payment = await session.scalar(
        select(Payment).where(Payment.stripe_payment_intent_id == intent_id)
    )
    return payment


async def _apply_success(session: AsyncSession, intent: dict[str, Any]) -> None:
    payment = await _payment_for(session, intent.get("id"))
    if payment is None or payment.status is PaymentStatus.SUCCEEDED:
        return  # Ya lo marcó la confirmación rápida, o no es un intent nuestro.
    booking = await session.get(Booking, payment.booking_id)
    if booking is None or booking.status is not BookingStatus.PENDING_PAYMENT:
        return
    await settle_payment(session, payment, booking, AuditActor.SYSTEM, None)


async def _apply_failure(session: AsyncSession, intent: dict[str, Any]) -> None:
    payment = await _payment_for(session, intent.get("id"))
    if payment and payment.status is PaymentStatus.PENDING:
        payment.status = PaymentStatus.FAILED


async def _apply_checkout_completed(session: AsyncSession, checkout: dict[str, Any]) -> None:
    """F4.6: el link de pago no tiene "confirmación rápida" del navegador; el webhook es la
    única fuente de verdad de que se pagó."""
    if checkout.get("payment_status") != "paid":
        return
    checkout_id = checkout.get("id")
    if not checkout_id:
        return
    payment = await session.scalar(
        select(Payment).where(Payment.stripe_checkout_session_id == checkout_id)
    )
    if payment is None or payment.status is PaymentStatus.SUCCEEDED:
        return
    booking = await session.get(Booking, payment.booking_id)
    if booking is None or booking.status is not BookingStatus.PENDING_PAYMENT:
        return
    await settle_payment(session, payment, booking, AuditActor.SYSTEM, None)


async def _apply_refund(session: AsyncSession, charge: dict[str, Any]) -> None:
    payment = await _payment_for(session, charge.get("payment_intent"))
    if payment is None:
        return
    payment.refunded_cents = min(int(charge.get("amount_refunded") or 0), payment.amount_cents)
    payment.status = (
        PaymentStatus.REFUNDED
        if payment.refunded_cents >= payment.amount_cents
        else PaymentStatus.PARTIALLY_REFUNDED
    )
