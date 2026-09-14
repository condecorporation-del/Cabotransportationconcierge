"""Listado de reservas del admin (F6.4): todos los estados por defecto, filtrable y paginado.

`service_date` no es una columna: los traslados la llevan en sus tramos y las actividades en
sus ítems, así que sale de una subconsulta correlacionada que junta las dos fuentes.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Literal

from sqlalchemy import ColumnElement, func, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Booking,
    BookingItem,
    BookingLeg,
    BookingSource,
    BookingStatus,
    BookingType,
    Customer,
    Hotel,
    Zone,
)

Sort = Literal["created_at", "service_date", "total_cents"]
Order = Literal["asc", "desc"]
MAX_PAGE_SIZE = 100


@dataclass
class BookingFilters:
    status: list[BookingStatus] | None = None
    source: BookingSource | None = None
    payment_method: str | None = None
    zone: str | None = None
    service_from: date | None = None
    service_to: date | None = None
    created_from: date | None = None
    created_to: date | None = None
    q: str | None = None


@dataclass
class BookingRow:
    id: uuid.UUID
    code: str
    status: BookingStatus
    booking_type: BookingType
    source: BookingSource
    payment_method: str | None
    currency: str
    total_cents: int
    service_date: date | None
    created_at: datetime
    customer_name: str
    customer_email: str
    customer_phone: str | None


def _service_date_column() -> ColumnElement[date | None]:
    leg_dates = select(
        BookingLeg.booking_id.label("booking_id"), BookingLeg.service_date.label("service_date")
    )
    item_dates = select(
        BookingItem.booking_id.label("booking_id"), BookingItem.service_date.label("service_date")
    ).where(BookingItem.service_date.is_not(None))
    all_dates = union_all(leg_dates, item_dates).subquery()
    return (
        select(func.min(all_dates.c.service_date))
        .where(all_dates.c.booking_id == Booking.id)
        .correlate(Booking)
        .scalar_subquery()
    )


async def list_bookings(
    session: AsyncSession,
    filters: BookingFilters,
    *,
    page: int,
    page_size: int,
    sort: Sort,
    order: Order,
) -> tuple[list[BookingRow], int]:
    page_size = min(page_size, MAX_PAGE_SIZE)
    service_date_col = _service_date_column().label("service_date")

    query = (
        select(
            Booking.id,
            Booking.code,
            Booking.status,
            Booking.booking_type,
            Booking.source,
            Booking.payment_method,
            Booking.currency,
            Booking.total_cents,
            Booking.created_at,
            Customer.name.label("customer_name"),
            Customer.email.label("customer_email"),
            Customer.phone.label("customer_phone"),
            service_date_col,
        )
        .join(Customer, Customer.id == Booking.customer_id)
        .where(Booking.deleted_at.is_(None))
    )

    if filters.status:
        query = query.where(Booking.status.in_(filters.status))
    if filters.source:
        query = query.where(Booking.source == filters.source)
    if filters.payment_method:
        query = query.where(Booking.payment_method == filters.payment_method)
    if filters.created_from:
        query = query.where(Booking.created_at >= datetime.combine(filters.created_from, time.min))
    if filters.created_to:
        query = query.where(
            Booking.created_at < datetime.combine(filters.created_to + timedelta(days=1), time.min)
        )
    if filters.service_from:
        query = query.where(service_date_col >= filters.service_from)
    if filters.service_to:
        query = query.where(service_date_col <= filters.service_to)
    if filters.zone:
        zone_bookings = (
            select(BookingLeg.booking_id)
            .join(Hotel, Hotel.id == BookingLeg.hotel_id)
            .join(Zone, Zone.id == Hotel.zone_id)
            .where(Zone.slug == filters.zone)
        )
        query = query.where(Booking.id.in_(zone_bookings))
    if filters.q:
        pattern = f"%{filters.q.strip()}%"
        flight_bookings = select(BookingLeg.booking_id).where(
            BookingLeg.flight_number.ilike(pattern)
        )
        query = query.where(
            or_(
                Booking.code.ilike(pattern),
                Customer.name.ilike(pattern),
                Customer.email.ilike(pattern),
                Customer.phone.ilike(pattern),
                Booking.id.in_(flight_bookings),
            )
        )

    total = await session.scalar(select(func.count()).select_from(query.subquery()))

    sort_columns: dict[Sort, Any] = {
        "created_at": Booking.created_at,
        "service_date": service_date_col,
        "total_cents": Booking.total_cents,
    }
    column = sort_columns[sort]
    query = query.order_by(column.asc() if order == "asc" else column.desc())
    query = query.limit(page_size).offset((page - 1) * page_size)

    rows = (await session.execute(query)).all()
    return [BookingRow(**row._mapping) for row in rows], total or 0
