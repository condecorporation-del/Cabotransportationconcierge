"""Reserva pública (WORKPLAN §8.1, F3.1): el precio se recalcula aquí y queda congelado."""

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
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
    LegType,
    ServiceScope,
    TripType,
    VehicleClass,
)
from app.schemas.bookings import ActivityBookingRequest, CustomerIn, TransferBookingRequest
from app.schemas.quotes import Language, Quote
from app.services.booking_codes import next_booking_code
from app.services.pricing import QuoteError, quote_activity, quote_transfer

AIRPORT = "SJD Los Cabos International Airport"
PICKUP_LEAD = {True: timedelta(hours=3), False: timedelta(hours=2)}


async def _customer_id(
    session: AsyncSession, company_id: uuid.UUID, customer: CustomerIn, language: Language
) -> uuid.UUID:
    """Un cliente por email (sin importar mayúsculas). Un dato nuevo no pisa uno ya guardado."""
    values = insert(Customer).values(
        company_id=company_id, language=language, **customer.model_dump()
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
    session: AsyncSession, request: TransferBookingRequest, quote: Quote, company: Company
) -> list[BookingLeg]:
    """Tramos con hora de pickup. Rechaza horarios dentro de la anticipación mínima (F3.3)."""
    settings = await session.get(CompanySettings, company.id)
    zone = ZoneInfo(company.timezone)
    earliest = datetime.now(zone) + timedelta(hours=settings.min_notice_hours if settings else 24)
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
            raise QuoteError("time_required", "Add the flight time for each transfer.")
        flight = datetime.combine(leg.service_date, leg.service_time, zone)
        # Salida: el chofer recoge antes del vuelo; la fecha del tramo es la del pickup.
        pickup = flight if kind is LegType.ARRIVAL else flight - PICKUP_LEAD[leg.international]
        if pickup < earliest:
            raise QuoteError("too_soon", "This date is too close. Contact us by WhatsApp.")
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
            )
        )
    return legs


async def create_booking(
    session: AsyncSession,
    request: TransferBookingRequest | ActivityBookingRequest,
    company: Company,
    idempotency_key: str | None,
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

    today = datetime.now(ZoneInfo(company.timezone)).date()
    legs: list[BookingLeg] = []
    if isinstance(request, ActivityBookingRequest):
        if request.service_date <= today:
            raise QuoteError("too_soon", "Activities are booked at least one day ahead.")
        quote = await quote_activity(session, request)
        booking_type = BookingType.ACTIVITY
    else:
        if request.service_scope is not ServiceScope.AIRPORT:
            raise QuoteError("scope_unavailable", "Local transfers are booked by WhatsApp.")
        quote = await quote_transfer(session, request, today)
        legs = await _transfer_legs(session, request, quote, company)
        booking_type = BookingType.TRANSFER

    items = [
        BookingItem(
            item_type=line.kind,
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
                description="Park fee, paid on site",
                unit_price_cents=quote.due_on_site_cents,
                total_cents=quote.due_on_site_cents,
            )
        )

    booking = Booking(
        code=await next_booking_code(session, company.id, today.year),
        status=BookingStatus.PENDING_PAYMENT,
        source=BookingSource.WEBSITE,
        booking_type=booking_type,
        customer_id=await _customer_id(session, company.id, request.customer, request.language),
        language=request.language,
        currency=quote.currency,
        subtotal_cents=quote.subtotal_cents,
        discount_cents=quote.discount_cents,
        tax_cents=quote.tax_cents,
        total_cents=quote.total_cents,
        promotion_id=quote._promotion_id,
        notes_customer=request.notes,
        idempotency_key=idempotency_key,
        legs=legs,
        items=items,
    )
    session.add(booking)
    await session.flush()
    return booking
