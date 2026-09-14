import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentCompany, DbSession, Stripe, client_ip
from app.api.v1.admin.deps import CurrentAdmin, require_csrf, require_role
from app.core.rate_limit import rate_limit
from app.models import (
    AdminRole,
    AdminUser,
    AuditLog,
    Booking,
    BookingSource,
    BookingStatus,
    Customer,
    Payment,
)
from app.schemas.admin_bookings import (
    AdminBookingDetail,
    AdminBookingOut,
    AdminBookingPage,
    AdminCancelIn,
    AdminManualBookingRequest,
    AdminPaymentOut,
    MarkPaidIn,
    TimelineEntryOut,
)
from app.schemas.bookings import BookingItemOut, BookingLegOut
from app.services.admin_actions import (
    cancel_booking,
    confirm_booking,
    delete_booking,
    mark_paid,
    mark_unpaid,
    resend_confirmation,
)
from app.services.admin_bookings import BookingFilters, Order, Sort, list_bookings
from app.services.bookings import create_manual_booking

router = APIRouter(
    prefix="/admin/bookings", tags=["admin-bookings"], dependencies=[Depends(rate_limit(60))]
)
NOT_FOUND = "Booking not found."
# Ver una reserva es cualquier rol; hacerle algo, cualquiera menos viewer (F6.5).
CAN_EDIT = require_role(AdminRole.OWNER, AdminRole.MANAGER, AdminRole.DISPATCHER, AdminRole.FINANCE)


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


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)])
async def create_route(
    body: AdminManualBookingRequest,
    company: CurrentCompany,
    admin: Annotated[AdminUser, Depends(CAN_EDIT)],
    session: DbSession,
    request: Request,
) -> AdminBookingDetail:
    """Reserva manual (F6.6): `payment` decide el estado de una vez, sin pasar por Stripe."""
    booking = await create_manual_booking(session, body, company, admin, client_ip(request))
    await session.commit()
    return await _to_detail(session, booking)


async def admin_booking(
    booking_id: Annotated[uuid.UUID, Path()], _admin: CurrentAdmin, session: DbSession
) -> Booking:
    # select(), no session.get(): un booking ya en el identity map ignoraría los `options`.
    booking = await session.scalar(
        select(Booking)
        .options(selectinload(Booking.legs), selectinload(Booking.items))
        .where(Booking.id == booking_id)
    )
    if booking is None or booking.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return booking


AdminBooking = Annotated[Booking, Depends(admin_booking)]


async def _to_detail(session: DbSession, booking: Booking) -> AdminBookingDetail:
    customer = await session.get(Customer, booking.customer_id)
    if customer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    payments = (
        await session.scalars(
            select(Payment).where(Payment.booking_id == booking.id).order_by(Payment.created_at)
        )
    ).all()
    return AdminBookingDetail(
        id=booking.id,
        code=booking.code,
        status=booking.status,
        booking_type=booking.booking_type,
        source=booking.source,
        payment_method=booking.payment_method,
        currency=booking.currency,
        subtotal_cents=booking.subtotal_cents,
        discount_cents=booking.discount_cents,
        tax_cents=booking.tax_cents,
        total_cents=booking.total_cents,
        deposit_cents=booking.deposit_cents,
        created_at=booking.created_at,
        notes_customer=booking.notes_customer,
        notes_internal=booking.notes_internal,
        customer_name=customer.name,
        customer_email=customer.email,
        customer_phone=customer.phone,
        legs=[BookingLegOut.model_validate(leg) for leg in booking.legs],
        items=[BookingItemOut.model_validate(item) for item in booking.items],
        payments=[AdminPaymentOut.model_validate(payment) for payment in payments],
    )


@router.get("/{booking_id}")
async def detail_route(booking: AdminBooking, session: DbSession) -> AdminBookingDetail:
    return await _to_detail(session, booking)


@router.get("/{booking_id}/timeline")
async def timeline_route(booking: AdminBooking, session: DbSession) -> list[TimelineEntryOut]:
    logs = await session.scalars(
        select(AuditLog)
        .where(AuditLog.entity == "booking", AuditLog.entity_id == booking.id)
        .order_by(AuditLog.created_at)
    )
    return [TimelineEntryOut.model_validate(log) for log in logs]


@router.post("/{booking_id}/confirm", dependencies=[Depends(require_csrf)])
async def confirm_route(
    booking: AdminBooking,
    admin: Annotated[AdminUser, Depends(CAN_EDIT)],
    session: DbSession,
    request: Request,
) -> AdminBookingDetail:
    """`OFFLINE_HOLD` o `PAID` -> `CONFIRMED`; cualquier otro estado, 409."""
    await confirm_booking(session, booking, admin, client_ip(request))
    await session.commit()
    return await _to_detail(session, booking)


@router.post("/{booking_id}/mark-paid", dependencies=[Depends(require_csrf)])
async def mark_paid_route(
    body: MarkPaidIn,
    booking: AdminBooking,
    admin: Annotated[AdminUser, Depends(CAN_EDIT)],
    session: DbSession,
    request: Request,
) -> AdminBookingDetail:
    """Pago recibido fuera de Stripe (efectivo, transferencia, cuenta)."""
    await mark_paid(session, booking, admin, body.provider, client_ip(request))
    await session.commit()
    return await _to_detail(session, booking)


@router.post("/{booking_id}/mark-unpaid", dependencies=[Depends(require_csrf)])
async def mark_unpaid_route(
    booking: AdminBooking,
    admin: Annotated[AdminUser, Depends(CAN_EDIT)],
    session: DbSession,
    request: Request,
) -> AdminBookingDetail:
    """Deshace un `mark-paid` manual marcado por error; un pago de Stripe se reembolsa."""
    await mark_unpaid(session, booking, admin, client_ip(request))
    await session.commit()
    return await _to_detail(session, booking)


@router.post("/{booking_id}/cancel", dependencies=[Depends(require_csrf)])
async def cancel_route(
    body: AdminCancelIn,
    booking: AdminBooking,
    admin: Annotated[AdminUser, Depends(CAN_EDIT)],
    session: DbSession,
    stripe: Stripe,
    request: Request,
) -> AdminBookingDetail:
    await cancel_booking(
        session, booking, admin, body.reason, body.refund, stripe, client_ip(request)
    )
    await session.commit()
    return await _to_detail(session, booking)


@router.post(
    "/{booking_id}/resend-confirmation",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def resend_confirmation_route(
    booking: AdminBooking, _admin: Annotated[AdminUser, Depends(CAN_EDIT)], session: DbSession
) -> None:
    await resend_confirmation(session, booking)
    await session.commit()


@router.delete(
    "/{booking_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_csrf)]
)
async def delete_route(
    booking: AdminBooking,
    admin: Annotated[AdminUser, Depends(CAN_EDIT)],
    session: DbSession,
    request: Request,
) -> None:
    await delete_booking(session, booking, admin, client_ip(request))
    await session.commit()
