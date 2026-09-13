from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentCompany, DbSession, client_ip
from app.core.rate_limit import rate_limit
from app.core.security import booking_token, read_booking_token
from app.models import Booking, Customer
from app.schemas.bookings import (
    BookingChange,
    BookingCreated,
    BookingDetail,
    BookingRequest,
    BookingSummary,
    BookingToken,
    CancelRequest,
)
from app.services.bookings import cancel_booking, change_booking, create_booking

router = APIRouter(prefix="/bookings", tags=["bookings"], dependencies=[Depends(rate_limit(10))])
bearer = HTTPBearer(auto_error=False)
NOT_FOUND = "Booking not found."


@router.post("", status_code=status.HTTP_201_CREATED)
async def create(
    body: BookingRequest,
    company: CurrentCompany,
    session: DbSession,
    request: Request,
    idempotency_key: Annotated[str | None, Header(min_length=8, max_length=80)] = None,
) -> BookingCreated:
    """Crea la reserva en `pending_payment`; el mismo `Idempotency-Key` no la duplica."""
    booking = await create_booking(session, body, company, idempotency_key, client_ip(request))
    await session.commit()
    summary = BookingSummary.model_validate(booking).model_dump()
    return BookingCreated(**summary, token=booking_token(company.id, booking.code))


@router.get(
    "/lookup",
    dependencies=[Depends(rate_limit(5))],
    responses={404: {"description": NOT_FOUND}},
)
async def lookup(
    company: CurrentCompany,
    session: DbSession,
    code: Annotated[str, Query(max_length=20)],
    email: Annotated[str, Query(max_length=254)],
) -> BookingToken:
    """My Trip: código + email. Si no existe o el email no coincide, la respuesta es la misma."""
    found = await session.scalar(
        select(Booking.code)
        .join(Customer, Customer.id == Booking.customer_id)
        .where(
            Booking.code == code.strip().upper(),
            func.lower(Customer.email) == email.strip().lower(),
            Booking.deleted_at.is_(None),
        )
    )
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return BookingToken(token=booking_token(company.id, found))


async def managed_booking(
    code: Annotated[str, Path(max_length=20)],
    company: CurrentCompany,
    session: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> Booking:
    """Reserva del token: alterado o expirado → 401; token de otra reserva → 404."""
    token_code = read_booking_token(credentials.credentials, company.id) if credentials else None
    if token_code is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "This link is invalid or expired. Find your booking with its code and email.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    booking = await session.scalar(
        select(Booking)
        .options(selectinload(Booking.legs), selectinload(Booking.items))
        .where(Booking.code == code, Booking.deleted_at.is_(None))
    )
    if token_code != code or booking is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return booking


ManagedBooking = Annotated[Booking, Depends(managed_booking)]


@router.get("/{code}")
async def detail(booking: ManagedBooking) -> BookingDetail:
    return BookingDetail.model_validate(booking)


@router.patch("/{code}")
async def change(
    body: BookingChange,
    booking: ManagedBooking,
    company: CurrentCompany,
    session: DbSession,
    request: Request,
) -> BookingDetail:
    """Cambios permitidos por política: vuelo, aerolínea, hora del vuelo y notas."""
    await change_booking(session, booking, company, body, client_ip(request))
    await session.commit()
    return BookingDetail.model_validate(booking)


@router.post("/{code}/cancel")
async def cancel(
    body: CancelRequest,
    booking: ManagedBooking,
    company: CurrentCompany,
    session: DbSession,
    request: Request,
) -> BookingDetail:
    """Cancelación del cliente según política; ya cancelada o completada → 409."""
    await cancel_booking(session, booking, company, body.reason, client_ip(request))
    await session.commit()
    return BookingDetail.model_validate(booking)
