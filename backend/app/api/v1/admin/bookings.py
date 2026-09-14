from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import DbSession
from app.api.v1.admin.deps import CurrentAdmin
from app.core.rate_limit import rate_limit
from app.models import BookingSource, BookingStatus
from app.schemas.admin_bookings import AdminBookingOut, AdminBookingPage
from app.services.admin_bookings import BookingFilters, Order, Sort, list_bookings

router = APIRouter(
    prefix="/admin/bookings", tags=["admin-bookings"], dependencies=[Depends(rate_limit(60))]
)


@router.get("")
async def list_route(
    _admin: CurrentAdmin,
    session: DbSession,
    status: Annotated[list[BookingStatus] | None, Query()] = None,
    source: BookingSource | None = None,
    payment_method: Annotated[str | None, Query(max_length=10)] = None,
    zone: Annotated[str | None, Query(max_length=60)] = None,
    service_from: date | None = None,
    service_to: date | None = None,
    created_from: date | None = None,
    created_to: date | None = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    sort: Sort = "created_at",
    order: Order = "desc",
) -> AdminBookingPage:
    """Sin filtro de estado, salen todos: una reserva recién creada siempre aparece (F6.4)."""
    filters = BookingFilters(
        status=status,
        source=source,
        payment_method=payment_method,
        zone=zone,
        service_from=service_from,
        service_to=service_to,
        created_from=created_from,
        created_to=created_to,
        q=q,
    )
    rows, total = await list_bookings(
        session, filters, page=page, page_size=page_size, sort=sort, order=order
    )
    return AdminBookingPage(
        items=[AdminBookingOut.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
