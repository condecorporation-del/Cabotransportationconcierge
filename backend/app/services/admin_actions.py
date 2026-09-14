"""Acciones del admin sobre una reserva ya creada (WORKPLAN §7.2, F6.5).

Cada acción es una transición de `booking_state.py` (o, para deshacer o reenviar, ninguna
transición) más el correo que le corresponde según §8.3. El admin que la hizo queda en
`audit_logs` vía `admin_user_id`.
"""

from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import booking_manage_url
from app.models import (
    AdminUser,
    AuditActor,
    AuditLog,
    Booking,
    BookingStatus,
    Customer,
    Payment,
    PaymentProvider,
    PaymentStatus,
)
from app.services.booking_state import transition
from app.services.bookings import notify_booking_event
from app.services.email import enqueue
from app.services.payments import PaymentError, amount_due, notify_confirmation, settle_payment
from app.services.stripe_gateway import StripeGateway

ManualProvider = Literal["cash", "bank_transfer", "manual", "account"]


async def confirm_booking(
    session: AsyncSession, booking: Booking, admin: AdminUser, ip: str | None
) -> None:
    """`OFFLINE_HOLD` o `PAID` -> `CONFIRMED`; cualquier otro estado, 409 (§8.2)."""
    transition(
        session,
        booking,
        BookingStatus.CONFIRMED,
        actor=AuditActor.ADMIN,
        admin_user_id=admin.id,
        ip=ip,
    )
    await notify_confirmation(session, booking)


async def mark_paid(
    session: AsyncSession,
    booking: Booking,
    admin: AdminUser,
    provider: ManualProvider,
    ip: str | None,
) -> None:
    """Pago recibido fuera de Stripe (efectivo, transferencia, cuenta); reusa `settle_payment`."""
    if booking.status is not BookingStatus.PENDING_PAYMENT:
        raise PaymentError("not_payable", "This booking is not waiting for a payment.")
    payment = Payment(
        booking_id=booking.id,
        provider=PaymentProvider(provider),
        status=PaymentStatus.PENDING,
        amount_cents=amount_due(booking),
        currency=booking.currency,
        received_by_admin_id=admin.id,
    )
    session.add(payment)
    await session.flush()
    await settle_payment(session, payment, booking, AuditActor.ADMIN, ip, admin_user_id=admin.id)


async def mark_unpaid(
    session: AsyncSession, booking: Booking, admin: AdminUser, ip: str | None
) -> None:
    """Deshace un `mark_paid` marcado por error; un pago de Stripe se reembolsa, no se deshace."""
    if booking.status is not BookingStatus.PAID:
        raise PaymentError("not_paid", "This booking is not marked as paid.")
    payment = await session.scalar(
        select(Payment)
        .where(Payment.booking_id == booking.id, Payment.status == PaymentStatus.SUCCEEDED)
        .order_by(Payment.created_at.desc())
    )
    if payment is None or payment.provider is PaymentProvider.STRIPE:
        raise PaymentError(
            "manual_payment_required",
            "Only a manually recorded payment can be undone this way; "
            "refund the Stripe payment instead.",
        )
    payment.status = PaymentStatus.CANCELLED
    transition(
        session,
        booking,
        BookingStatus.PENDING_PAYMENT,
        actor=AuditActor.ADMIN,
        admin_user_id=admin.id,
        ip=ip,
    )


async def cancel_booking(
    session: AsyncSession,
    booking: Booking,
    admin: AdminUser,
    reason: str | None,
    refund: bool,
    gateway: StripeGateway,
    ip: str | None,
) -> None:
    """Cancela con o sin reembolso (§8.2: cualquier estado salvo `COMPLETED`)."""
    if refund:
        payment = await session.scalar(
            select(Payment)
            .where(
                Payment.booking_id == booking.id,
                Payment.status.in_((PaymentStatus.SUCCEEDED, PaymentStatus.PARTIALLY_REFUNDED)),
            )
            .order_by(Payment.created_at.desc())
        )
        if payment is None:
            raise PaymentError("nothing_to_refund", "This booking has no payment to refund.")
        if payment.provider is not PaymentProvider.STRIPE or not payment.stripe_payment_intent_id:
            raise PaymentError(
                "manual_refund_required",
                "Refund this payment yourself; it wasn't charged through Stripe.",
            )
        result = await gateway.create_refund(
            payment_intent=payment.stripe_payment_intent_id,
            amount_cents=None,
            idempotency_key=f"booking-cancel-refund:{booking.id}",
        )
        payment.refunded_cents = min(
            payment.refunded_cents + int(result.get("amount") or 0), payment.amount_cents
        )
        payment.status = (
            PaymentStatus.REFUNDED
            if payment.refunded_cents >= payment.amount_cents
            else PaymentStatus.PARTIALLY_REFUNDED
        )
    transition(
        session,
        booking,
        BookingStatus.CANCELLED,
        actor=AuditActor.ADMIN,
        admin_user_id=admin.id,
        reason=reason,
        ip=ip,
    )
    await notify_booking_event(
        session, booking, "booking_cancelled", "booking_cancelled_ops", {"reason": reason}
    )


async def resend_confirmation(session: AsyncSession, booking: Booking) -> None:
    """No es una transición: reenvía el correo que ya le tocaba al estado actual."""
    if booking.status is BookingStatus.CANCELLED:
        raise AppError("nothing_to_resend", "A cancelled booking has no confirmation to resend.")
    if booking.status is not BookingStatus.PENDING_PAYMENT:
        await notify_confirmation(session, booking)
        return
    customer = await session.get(Customer, booking.customer_id)
    if customer is None:
        return
    await enqueue(
        session,
        booking.company_id,
        "booking_pending_payment",
        [customer.email],
        {"code": booking.code, "manage_url": booking_manage_url(booking.company_id, booking.code)},
        booking.language,
        booking.id,
    )


async def delete_booking(
    session: AsyncSession, booking: Booking, admin: AdminUser, ip: str | None
) -> None:
    """Borrado lógico (§7.2): no libera el código ni toca el estado, solo la oculta del listado."""
    if booking.deleted_at is not None:
        return
    booking.deleted_at = datetime.now(UTC)
    session.add(
        AuditLog(
            actor=AuditActor.ADMIN,
            admin_user_id=admin.id,
            action="deleted",
            entity="booking",
            entity_id=booking.id,
            ip=ip,
        )
    )
