"""Máquina de estados de la reserva (WORKPLAN §8.2). El `status` solo cambia por aquí."""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import AuditActor, AuditLog, Booking, BookingStatus

S = BookingStatus
TRANSITIONS: dict[BookingStatus, frozenset[BookingStatus]] = {
    S.PENDING_PAYMENT: frozenset({S.PAID, S.CANCELLED}),
    S.OFFLINE_HOLD: frozenset({S.CONFIRMED, S.PENDING_PAYMENT, S.CANCELLED}),
    # PAID -> PENDING_PAYMENT: no está en el diagrama original de §8.2; se agregó en F6.5 para
    # que el admin pueda deshacer un `mark-paid` manual marcado por error (nunca uno de Stripe).
    S.PAID: frozenset({S.CONFIRMED, S.COMPLETED, S.CANCELLED, S.PENDING_PAYMENT}),
    S.CONFIRMED: frozenset({S.COMPLETED, S.CANCELLED}),
    S.COMPLETED: frozenset(),
    S.CANCELLED: frozenset(),
}


class TransitionError(AppError):
    """Transición fuera de la tabla de §8.2."""

    status_code = 409

    def __init__(self, current: BookingStatus, target: BookingStatus) -> None:
        super().__init__(
            "invalid_transition", f"A {current.value} booking cannot change to {target.value}."
        )


def transition(
    session: AsyncSession,
    booking: Booking,
    target: BookingStatus,
    *,
    actor: AuditActor,
    admin_user_id: uuid.UUID | None = None,
    reason: str | None = None,
    ip: str | None = None,
) -> None:
    """Cambia el estado y deja el registro de auditoría en la misma transacción."""
    current = booking.status
    if target not in TRANSITIONS[current]:
        raise TransitionError(current, target)
    booking.status = target
    if target is S.CANCELLED:
        booking.cancelled_at = datetime.now(UTC)
        booking.cancel_reason = reason
    session.add(
        AuditLog(
            actor=actor,
            admin_user_id=admin_user_id,
            action="status_change",
            entity="booking",
            entity_id=booking.id,
            before={"status": current.value},
            after={"status": target.value, "reason": reason},
            ip=ip,
        )
    )
