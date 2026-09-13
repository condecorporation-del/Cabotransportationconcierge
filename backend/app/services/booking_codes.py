import uuid

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BookingCodeCounter


async def next_booking_code(
    session: AsyncSession, company_id: uuid.UUID, year: int, prefix: str = "CTC"
) -> str:
    """Siguiente código `CTC-2026-000001`, sin colisiones aunque lleguen reservas simultáneas.

    Un solo INSERT ... ON CONFLICT DO UPDATE incrementa y devuelve el número: Postgres bloquea la
    fila del contador hasta el commit, así que dos transacciones nunca obtienen el mismo valor
    (ClassVIP usaba COUNT(*) y chocaba, WORKPLAN E7).
    """
    first = insert(BookingCodeCounter).values(company_id=company_id, year=year, last_value=1)
    increment = first.on_conflict_do_update(
        index_elements=[BookingCodeCounter.company_id, BookingCodeCounter.year],
        set_={"last_value": BookingCodeCounter.last_value + 1},
    ).returning(BookingCodeCounter.last_value)
    number = (await session.execute(increment)).scalar_one()
    return f"{prefix}-{year}-{number:06d}"
