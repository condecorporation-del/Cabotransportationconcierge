"""Cuentas por cobrar: el saldo nunca se guarda, se calcula de cargos y abonos (F6.8)."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import AccountCharge, AccountPayment, Booking, ChargeStatus, ClientAccount


async def balance(session: AsyncSession, account_id: uuid.UUID) -> int:
    charged = await session.scalar(
        select(func.coalesce(func.sum(AccountCharge.amount_cents), 0)).where(
            AccountCharge.account_id == account_id, AccountCharge.status != ChargeStatus.VOID
        )
    )
    paid = await session.scalar(
        select(func.coalesce(func.sum(AccountPayment.amount_cents), 0)).where(
            AccountPayment.account_id == account_id
        )
    )
    return int(charged or 0) - int(paid or 0)


async def charge_booking(
    session: AsyncSession, account: ClientAccount, booking_id: uuid.UUID
) -> AccountCharge:
    """Factura a la cuenta una reserva que ya existía, sin tocar su estado ni su pago."""
    booking = await session.get(Booking, booking_id)
    if booking is None or booking.customer_id != account.customer_id:
        raise AppError("booking_not_found", "That booking does not belong to this customer.")
    already_charged = await session.scalar(
        select(AccountCharge.id).where(AccountCharge.booking_id == booking_id)
    )
    if already_charged is not None:
        raise AppError("already_charged", "This booking is already charged to an account.")
    charge = AccountCharge(
        account_id=account.id,
        booking_id=booking.id,
        description=f"Booking {booking.code}",
        amount_cents=booking.total_cents,
    )
    session.add(charge)
    return charge
