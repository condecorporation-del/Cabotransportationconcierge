"""Reservas públicas (WORKPLAN §8.1, F3.1 a F3.7): el precio se recalcula aquí y queda congelado."""

import uuid
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import booking_manage_url
from app.models import (
    AuditActor,
    AuditLog,
    Booking,
    BookingItem,
    BookingLeg,
    BookingSource,
    BookingStatus,
    BookingType,
    Company,
    CompanySettings,
    Customer,
    Hotel,
    ItemType,
    LegStatus,
    LegType,
    ServiceScope,
    TripType,
    VehicleClass,
)
from app.schemas.bookings import (
    ActivityBookingRequest,
    BookingChange,
    BookingLegOut,
    CustomerIn,
    TransferBookingRequest,
)
from app.schemas.quotes import Language, Quote
from app.services.booking_codes import next_booking_code
from app.services.booking_state import TRANSITIONS, transition
from app.services.email import enqueue
from app.services.pricing import night_hours, quote_activity, quote_transfer

AIRPORT = "SJD Los Cabos International Airport"
PICKUP_LEAD = {True: timedelta(hours=3), False: timedelta(hours=2)}
EDITABLE = frozenset(
    {
        BookingStatus.PENDING_PAYMENT,
        BookingStatus.OFFLINE_HOLD,
        BookingStatus.CONFIRMED,
        BookingStatus.PAID,
    }
)


async def company_settings(session: AsyncSession, company_id: uuid.UUID) -> CompanySettings:
    settings = await session.get(CompanySettings, company_id)
    if settings is None:
        raise RuntimeError("La empresa no tiene company_settings")
    return settings


def _start(leg: BookingLeg, zone: ZoneInfo) -> datetime:
    return datetime.combine(leg.service_date, leg.pickup_time or leg.service_time or time.min, zone)


async def _customer_id(
    session: AsyncSession, company_id: uuid.UUID, customer: CustomerIn, language: Language
) -> uuid.UUID:
    """Un cliente por email (sin importar mayúsculas). Un dato nuevo no pisa uno ya guardado."""
    fields = customer.model_dump(exclude={"first_name", "last_name", "confirm_email"})
    values = insert(Customer).values(
        company_id=company_id, language=language, name=customer.name, **fields
    )
    statement = values.on_conflict_do_update(
        index_elements=[Customer.company_id, func.lower(Customer.email)],
        set_={
            "phone": func.coalesce(Customer.phone, values.excluded.phone),
            "country": func.coalesce(Customer.country, values.excluded.country),
            "marketing_opt_in": Customer.marketing_opt_in | values.excluded.marketing_opt_in,
            "language": values.excluded.language,
            "updated_at": func.now(),
        },
    ).returning(Customer.id)
    return (await session.execute(statement)).scalar_one()


async def _transfer_legs(
    session: AsyncSession,
    request: TransferBookingRequest,
    quote: Quote,
    company: Company,
    settings: CompanySettings,
) -> list[BookingLeg]:
    """Tramos con hora de pickup. Rechaza horarios dentro de la anticipación mínima (F3.3)."""
    zone = ZoneInfo(company.timezone)
    earliest = datetime.now(zone) + timedelta(hours=settings.min_notice_hours)
    hotel = (
        await session.execute(select(Hotel.name).where(Hotel.id == request.hotel_id))
    ).scalar_one()
    vehicle_id = (
        await session.execute(
            select(VehicleClass.id).where(VehicleClass.code == quote.vehicle_class)
        )
    ).scalar_one()
    kinds = (
        [LegType.ARRIVAL, LegType.DEPARTURE]
        if request.trip_type is TripType.ROUND_TRIP
        else [LegType(request.direction)]
    )
    legs = []
    for kind, leg in zip(kinds, request.legs, strict=True):
        if leg.service_time is None:
            raise AppError("time_required", "Add the flight time for each transfer.")
        flight = datetime.combine(leg.service_date, leg.service_time, zone)
        if kind is LegType.ARRIVAL:
            pickup = flight
        elif leg.pickup_time is not None:
            # Hora editada por el cliente: mismo día, o el anterior si cruza la medianoche.
            pickup = datetime.combine(flight.date(), leg.pickup_time, zone)
            if pickup >= flight:
                pickup -= timedelta(days=1)
        else:
            # Hora sugerida: el chofer recoge antes del vuelo (WORKPLAN §3.5.5).
            pickup = flight - PICKUP_LEAD[leg.international]
        if pickup < earliest:
            raise AppError("too_soon", "This date is too close. Contact us by WhatsApp.")
        legs.append(
            BookingLeg(
                leg_type=kind,
                service_date=pickup.date(),
                service_time=leg.service_time,
                pickup_time=pickup.time(),
                flight_number=leg.flight_number,
                airline=leg.airline,
                origin=AIRPORT if kind is LegType.ARRIVAL else hotel,
                destination=hotel if kind is LegType.ARRIVAL else AIRPORT,
                hotel_id=request.hotel_id,
                pax_adults=request.passengers,
                vehicle_class_id=vehicle_id,
                vehicle_count=quote.vehicle_count,
            )
        )
    return legs


async def create_booking(
    session: AsyncSession,
    request: TransferBookingRequest | ActivityBookingRequest,
    company: Company,
    idempotency_key: str | None,
    ip: str | None = None,
) -> Booking:
    if idempotency_key:
        # Dos POST con la misma clave se forman; el segundo encuentra la reserva del primero.
        lock = func.hashtextextended(f"booking:{company.id}:{idempotency_key}", 0)
        await session.execute(select(func.pg_advisory_xact_lock(lock)))
        existing = await session.scalar(
            select(Booking)
            .options(selectinload(Booking.items))
            .where(Booking.idempotency_key == idempotency_key)
        )
        if existing:
            return existing

    settings = await company_settings(session, company.id)
    if request.accepted_terms_version != settings.terms_version:
        raise AppError(
            "terms_outdated", "Please accept the current terms and conditions and try again."
        )

    today = datetime.now(ZoneInfo(company.timezone)).date()
    legs: list[BookingLeg] = []
    activity_date = None
    payment_method: str | None = None
    status = BookingStatus.PENDING_PAYMENT
    if isinstance(request, ActivityBookingRequest):
        if request.service_date <= today:
            raise AppError("too_soon", "Activities are booked at least one day ahead.")
        quote = await quote_activity(session, request)
        booking_type = BookingType.ACTIVITY
        activity_date = request.service_date
    else:
        if request.service_scope is not ServiceScope.AIRPORT:
            raise AppError("scope_unavailable", "Local transfers are booked by WhatsApp.")
        quote = await quote_transfer(session, request, today)
        legs = await _transfer_legs(session, request, quote, company, settings)
        booking_type = BookingType.TRANSFER
        payment_method = request.payment
        # Cash sin depósito (WORKPLAN §3.5.5, F3.13): se confirma sin pago en línea; el chofer
        # cobra en efectivo. Con depósito (Escalade, Limousine) sigue pendiente hasta pagarlo.
        if request.payment == "cash" and quote.deposit_cents == 0:
            status = BookingStatus.CONFIRMED

    items = [
        BookingItem(
            item_type=line.kind,
            service_date=activity_date,
            description=line.description[:200],
            quantity=line.quantity,
            unit_price_cents=line.unit_price_cents,
            total_cents=line.total_cents,
        )
        for line in quote.lines
    ]
    if quote.due_on_site_cents:
        # Informativo: se paga en sitio y no suma al total de la reserva.
        items.append(
            BookingItem(
                item_type=ItemType.PARK_FEE,
                service_date=activity_date,
                description="Park fee, paid on site",
                unit_price_cents=quote.due_on_site_cents,
                total_cents=quote.due_on_site_cents,
            )
        )

    booking = Booking(
        code=await next_booking_code(session, company.id, today.year),
        status=status,
        source=BookingSource.WEBSITE,
        booking_type=booking_type,
        customer_id=await _customer_id(session, company.id, request.customer, request.language),
        language=request.language,
        currency=quote.currency,
        subtotal_cents=quote.subtotal_cents,
        discount_cents=quote.discount_cents,
        tax_cents=quote.tax_cents,
        total_cents=quote.total_cents,
        deposit_cents=quote.deposit_cents,
        promotion_id=quote._promotion_id,
        notes_customer=request.notes,
        idempotency_key=idempotency_key,
        terms_version=request.accepted_terms_version,
        payment_method=payment_method,
        utm=request.attribution.model_dump(exclude_none=True),
        legs=legs,
        items=items,
    )
    session.add(booking)
    await session.flush()
    session.add(
        AuditLog(
            actor=AuditActor.CUSTOMER,
            action="create",
            entity="booking",
            entity_id=booking.id,
            after={
                "code": booking.code,
                "status": booking.status.value,
                "total": booking.total_cents,
            },
            ip=ip,
        )
    )
    await _notify_created(session, booking, request.customer, payment_method)
    return booking


async def _notify_created(
    session: AsyncSession, booking: Booking, customer: CustomerIn, payment_method: str | None
) -> None:
    """F5.4, F5.5: al cliente según el estado con el que nació; a la empresa, siempre."""
    manage_url = booking_manage_url(booking.company_id, booking.code)
    if booking.status is BookingStatus.CONFIRMED:
        template, context = (
            "booking_confirmed",
            {
                "code": booking.code,
                "manage_url": manage_url,
                "voucher_url": manage_url,
                "balance_note": None,
            },
        )
    else:
        template, context = (
            "booking_pending_payment",
            {"code": booking.code, "manage_url": manage_url},
        )
    await enqueue(
        session,
        booking.company_id,
        template,
        [customer.email],
        context,
        booking.language,
        booking.id,
    )
    settings = get_settings()
    if settings.email_ops_to:
        total = f"${booking.total_cents / 100:,.2f} {booking.currency}"
        await enqueue(
            session,
            booking.company_id,
            "booking_new",
            [settings.email_ops_to],
            {
                "code": booking.code,
                "customer_name": customer.name,
                "total_display": total,
                "payment_method": payment_method or "activity",
            },
            booking_id=booking.id,
        )


def _snapshot(booking: Booking) -> dict[str, Any]:
    legs = {leg.leg_type.value: BookingLegOut.model_validate(leg) for leg in booking.legs}
    return {kind: leg.model_dump(mode="json") for kind, leg in legs.items()} | {
        "notes": booking.notes_customer
    }


async def change_booking(
    session: AsyncSession,
    booking: Booking,
    company: Company,
    change: BookingChange,
    ip: str | None,
) -> None:
    """Cambios del cliente (F3.7): vuelo, aerolínea, hora y notas hasta `change_hours` antes.

    Una hora nueva mueve el pickup con la misma anticipación; si cambia el precio
    (entra o sale del recargo nocturno) se rechaza.
    """
    if booking.status not in EDITABLE:
        raise AppError("not_editable", "This booking can no longer be changed.")
    settings = await company_settings(session, company.id)
    zone = ZoneInfo(company.timezone)
    limit = datetime.now(zone) + timedelta(hours=settings.change_hours)
    window = AppError(
        "change_window",
        f"Changes are possible up to {settings.change_hours} hours before pickup. "
        "Contact us by WhatsApp.",
    )
    night = (settings.night_surcharge_start, settings.night_surcharge_end)
    before = _snapshot(booking)
    legs = {leg.leg_type: leg for leg in booking.legs}
    for update in change.legs:
        leg = legs.get(update.leg_type)
        if leg is None:
            raise AppError("leg_not_found", f"This booking has no {update.leg_type.value} leg.")
        pickup = _start(leg, zone)
        if pickup < limit:
            raise window
        if update.service_time and leg.service_time and update.service_time != leg.service_time:
            if night_hours(update.service_time, *night) != night_hours(leg.service_time, *night):
                raise AppError("price_change", "That time changes the price. Contact us.")
            flight = datetime.combine(leg.service_date, leg.service_time, zone)
            flight += timedelta(days=1) if flight < pickup else timedelta()
            new_pickup = datetime.combine(flight.date(), update.service_time, zone) - (
                flight - pickup
            )
            if new_pickup < limit:
                raise window
            leg.service_date, leg.pickup_time = new_pickup.date(), new_pickup.time()
            leg.service_time = update.service_time
        leg.flight_number = update.flight_number or leg.flight_number
        leg.airline = update.airline or leg.airline
    if "notes" in change.model_fields_set:
        booking.notes_customer = change.notes
    session.add(
        AuditLog(
            actor=AuditActor.CUSTOMER,
            action="customer_change",
            entity="booking",
            entity_id=booking.id,
            before=before,
            after=_snapshot(booking),
            ip=ip,
        )
    )
    await _notify(session, booking, "booking_changed", "booking_changed_ops", {})


async def _notify(
    session: AsyncSession, booking: Booking, customer_template: str, ops_template: str, extra: Any
) -> None:
    """F5.6: mismo patrón para cambios y cancelaciones, al cliente y a la empresa."""
    customer = await session.get(Customer, booking.customer_id)
    context = {
        "code": booking.code,
        "manage_url": booking_manage_url(booking.company_id, booking.code),
    }
    context |= extra
    if customer:
        await enqueue(
            session,
            booking.company_id,
            customer_template,
            [customer.email],
            context,
            booking.language,
            booking.id,
        )
    settings = get_settings()
    if settings.email_ops_to:
        await enqueue(
            session,
            booking.company_id,
            ops_template,
            [settings.email_ops_to],
            context,
            booking_id=booking.id,
        )


async def cancel_booking(
    session: AsyncSession, booking: Booking, company: Company, reason: str | None, ip: str | None
) -> None:
    """Cancelación del cliente (F3.7) hasta `cancellation_hours` antes del primer servicio."""
    settings = await company_settings(session, company.id)
    zone = ZoneInfo(company.timezone)
    starts = [_start(leg, zone) for leg in booking.legs if leg.status is LegStatus.SCHEDULED]
    starts += [
        datetime.combine(i.service_date, time.min, zone) for i in booking.items if i.service_date
    ]
    limit = datetime.now(zone) + timedelta(hours=settings.cancellation_hours)
    if BookingStatus.CANCELLED in TRANSITIONS[booking.status] and starts and min(starts) < limit:
        raise AppError(
            "cancel_window",
            f"Online cancellation closes {settings.cancellation_hours} hours before the service. "
            "Contact us by WhatsApp.",
        )
    transition(
        session, booking, BookingStatus.CANCELLED, actor=AuditActor.CUSTOMER, reason=reason, ip=ip
    )
    for leg in booking.legs:
        leg.status = LegStatus.CANCELLED
    await _notify(
        session, booking, "booking_cancelled", "booking_cancelled_ops", {"reason": reason}
    )
