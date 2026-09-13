from typing import Annotated

from fastapi import APIRouter, Depends, Header, status

from app.api.deps import CurrentCompany, DbSession
from app.core.rate_limit import rate_limit
from app.schemas.bookings import BookingCreated, BookingRequest
from app.services.bookings import create_booking

router = APIRouter(prefix="/bookings", tags=["bookings"], dependencies=[Depends(rate_limit(10))])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create(
    body: BookingRequest,
    company: CurrentCompany,
    session: DbSession,
    idempotency_key: Annotated[str | None, Header(min_length=8, max_length=80)] = None,
) -> BookingCreated:
    """Crea la reserva en `pending_payment`; el mismo `Idempotency-Key` no la duplica."""
    booking = await create_booking(session, body, company, idempotency_key)
    await session.commit()
    return BookingCreated.model_validate(booking)
