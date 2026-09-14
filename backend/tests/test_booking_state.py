import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditActor, AuditLog, Booking, BookingStatus
from app.services.booking_state import TransitionError, transition
from tests.test_bookings import URL, _transfer

S = BookingStatus
# Tabla de WORKPLAN §8.2, escrita a mano para que el test no se valide contra sí mismo.
ALLOWED = {
    (S.PENDING_PAYMENT, S.PAID),
    (S.PENDING_PAYMENT, S.CANCELLED),
    (S.OFFLINE_HOLD, S.CONFIRMED),
    (S.OFFLINE_HOLD, S.PENDING_PAYMENT),
    (S.OFFLINE_HOLD, S.CANCELLED),
    (S.PAID, S.CONFIRMED),
    (S.PAID, S.COMPLETED),
    (S.PAID, S.CANCELLED),
    (S.PAID, S.PENDING_PAYMENT),  # F6.5: corrige un mark-paid manual marcado por error
    (S.CONFIRMED, S.COMPLETED),
    (S.CONFIRMED, S.CANCELLED),
}


@pytest.mark.parametrize("current", list(S))
@pytest.mark.parametrize("target", list(S))
async def test_every_transition_follows_the_table(
    db: AsyncSession, current: BookingStatus, target: BookingStatus
) -> None:
    booking = Booking(id=uuid.uuid4(), status=current)
    if (current, target) not in ALLOWED:
        with pytest.raises(TransitionError):
            transition(db, booking, target, actor=AuditActor.SYSTEM)
        assert booking.status is current
        return
    transition(db, booking, target, actor=AuditActor.SYSTEM)
    assert booking.status is target
    [log] = [obj for obj in db.new if isinstance(obj, AuditLog)]
    assert (log.before, log.after["status"]) == ({"status": current.value}, target.value)


async def test_cancellation_is_audited(api: AsyncClient, db: AsyncSession) -> None:
    code = (await api.post(URL, json=await _transfer(db))).json()["code"]
    booking = await db.scalar(select(Booking).where(Booking.code == code))
    assert booking is not None
    transition(db, booking, S.CANCELLED, actor=AuditActor.CUSTOMER, reason="Flight cancelled")
    await db.flush()
    log = await db.scalar(
        select(AuditLog).where(AuditLog.entity_id == booking.id, AuditLog.action == "status_change")
    )
    assert log is not None
    assert (log.actor, log.after["reason"]) == (AuditActor.CUSTOMER, "Flight cancelled")
    assert booking.cancelled_at is not None
