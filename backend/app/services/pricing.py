"""Motor único de precios (WORKPLAN D8): web, admin, IA y Stripe cotizan solo aquí.

Reglas iguales a la referencia (WORKPLAN §3.5.4 y §3.5.5; ejemplos en ADR-002):
- Unidades = ceil(pasajeros / capacidad). Nunca se rechaza por capacidad; se cotizan varias.
- Sin vehículo elegido ("Any type of Vehicle") se toma el de menor total.
- Pasajeros arriba de `included_pax` pagan `extra_pax_cents` por unidad y por tramo (limusina).
- Extras con unidades gratis, precio por vehículo y la regla "una por vehículo".
- Recargo nocturno: horas nocturnas de cada tramo por `extra_hour_cents` del vehículo.
- Una sola promoción (la de mayor descuento), sobre la tarifa base de todas las unidades.
- IVA con tarjeta sobre el total con descuento; en efectivo o salidas al aeropuerto no aplica.
"""

import uuid
from datetime import date, time
from typing import Any

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.errors import AppError
from app.models import (
    Activity,
    ActivityPackage,
    Company,
    CompanySettings,
    DiscountType,
    Extra,
    Hotel,
    ItemType,
    Promotion,
    PromotionScope,
    Rate,
    ServiceScope,
    TripType,
    VehicleClass,
    Zone,
)
from app.schemas.quotes import ActivityQuoteRequest, Quote, QuoteLine, TransferQuoteRequest

# La primera hora nocturna cubre 75 minutos; después se cobra cada hora iniciada.
FIRST_NIGHT_BLOCK_MINUTES = 75


class QuoteError(AppError):
    """No se puede cotizar con estos datos (hotel, vehículo, extras, promoción)."""


def night_hours(moment: time | None, start: time, end: time) -> int:
    """Horas de recargo de un servicio a esa hora: 23:00 → 1, 00:15 → 2, 04:59 → 6, 05:00 → 0."""
    if moment is None:
        return 0

    def minutes(value: time) -> int:
        return value.hour * 60 + value.minute

    span = (minutes(end) - minutes(start)) % 1440
    elapsed = (minutes(moment) - minutes(start)) % 1440
    if elapsed >= span:
        return 0
    if elapsed < FIRST_NIGHT_BLOCK_MINUTES:
        return 1
    return (elapsed - FIRST_NIGHT_BLOCK_MINUTES) // 60 + 2


def _text(i18n: dict[str, Any], language: str) -> str:
    return str(i18n.get(language) or i18n.get("en") or "")


def _company_id(session: AsyncSession) -> uuid.UUID:
    company_id: uuid.UUID | None = session.info.get("company_id")
    if company_id is None:
        raise RuntimeError("La sesión no tiene empresa (session.info['company_id'])")
    return company_id


def _units(passengers: int, vehicle: VehicleClass) -> int:
    return -(-passengers // vehicle.max_pax)


async def _vehicle_and_rate(
    session: AsyncSession, zone_id: uuid.UUID, request: TransferQuoteRequest
) -> tuple[VehicleClass, Rate, int]:
    query = (
        select(VehicleClass, Rate)
        .join(Rate, Rate.vehicle_class_id == VehicleClass.id)
        .where(
            VehicleClass.is_active,
            Rate.is_active,
            Rate.zone_id == zone_id,
            Rate.trip_type == request.trip_type,
            Rate.service_scope == request.service_scope,
        )
    )
    if request.vehicle_class:
        query = query.where(VehicleClass.code == request.vehicle_class)
    options = (await session.execute(query)).tuples().all()
    if not options:
        raise QuoteError("rate_unavailable", "Rate unavailable. Try another vehicle or contact us.")
    vehicle, rate = min(
        options,
        key=lambda row: (row[1].price_cents * _units(request.passengers, row[0]), row[0].sort),
    )
    return vehicle, rate, _units(request.passengers, vehicle)


def _window(
    column: InstrumentedAttribute[date | None], day: date, *, upper: bool
) -> ColumnElement[bool]:
    return or_(column.is_(None), column >= day if upper else column <= day)


async def _promotion(
    session: AsyncSession,
    code: str | None,
    travel_date: date,
    today: date,
    base_cents: int,
    subtotal_cents: int,
) -> tuple[Promotion | None, int]:
    candidates = (
        await session.scalars(
            select(Promotion).where(
                Promotion.is_active,
                or_(Promotion.code.is_(None), func.lower(Promotion.code) == (code or "").lower()),
                _window(Promotion.travel_from, travel_date, upper=False),
                _window(Promotion.travel_to, travel_date, upper=True),
                _window(Promotion.book_from, today, upper=False),
                _window(Promotion.book_to, today, upper=True),
                or_(Promotion.max_uses.is_(None), Promotion.used_count < Promotion.max_uses),
            )
        )
    ).all()
    if code and not any(p.code for p in candidates):
        raise QuoteError("invalid_promo_code", "This promo code is not valid for these dates.")

    def discount(promo: Promotion) -> int:
        scope = base_cents if promo.applies_to is PromotionScope.TRANSFER_BASE else subtotal_cents
        amount = (
            (scope * promo.value + 50) // 100
            if promo.discount_type is DiscountType.PERCENT
            else promo.value
        )
        return min(amount, scope)

    best = max(candidates, key=discount, default=None)
    return best, discount(best) if best else 0


def _line(
    kind: ItemType, code: str | None, description: str, quantity: int, unit: int
) -> QuoteLine:
    return QuoteLine(
        kind=kind,
        code=code,
        description=description,
        quantity=quantity,
        unit_price_cents=unit,
        total_cents=quantity * unit,
    )


async def quote_transfer(
    session: AsyncSession, request: TransferQuoteRequest, today: date
) -> Quote:
    company_id = _company_id(session)
    row = (
        await session.execute(
            select(Hotel, Zone.slug)
            .join(Zone, Zone.id == Hotel.zone_id)
            .where(Hotel.id == request.hotel_id, Hotel.is_active, Zone.is_active)
        )
    ).first()
    if row is None:
        raise QuoteError("hotel_not_found", "We could not find that hotel.")
    hotel, zone_slug = row
    departure_only = (
        request.service_scope is ServiceScope.AIRPORT
        and request.trip_type is TripType.ONE_WAY
        and request.direction == "departure"
    )
    if request.payment == "cash" and departure_only:
        raise QuoteError(
            "cash_unavailable", "Cash payment is not available for airport departures."
        )

    vehicle, rate, units = await _vehicle_and_rate(session, hotel.zone_id, request)
    legs = len(request.legs)
    es = request.language == "es"
    trip = {
        (TripType.ONE_WAY, False): "one way",
        (TripType.ROUND_TRIP, False): "round trip",
        (TripType.ONE_WAY, True): "sencillo",
        (TripType.ROUND_TRIP, True): "redondo",
    }[(request.trip_type, es)]
    base = rate.price_cents * units
    lines = [
        _line(ItemType.TRANSFER, vehicle.code, f"{vehicle.name}, {trip}", units, rate.price_cents)
    ]

    if vehicle.included_pax and vehicle.extra_pax_cents:
        extra_pax = request.passengers - vehicle.included_pax * units
        if extra_pax > 0:
            label = "Pasajeros adicionales" if es else "Additional passengers"
            count = extra_pax * units * legs
            lines.append(
                _line(ItemType.EXTRA, "EXTRA_PASSENGERS", label, count, vehicle.extra_pax_cents)
            )

    requested = {extra.code: extra.quantity for extra in request.extras}
    extras = (
        await session.scalars(select(Extra).where(Extra.is_active, Extra.code.in_(requested)))
    ).all()
    by_code = {extra.code: extra for extra in extras}
    for code, quantity in requested.items():
        extra = by_code.get(code)
        if extra is None or extra.included or extra.auto_rule is not None:
            raise QuoteError("extra_unavailable", f"The extra {code} is not available.")
        name = _text(extra.name, request.language)
        if quantity > extra.max_qty:
            raise QuoteError("extra_quantity", f"{_text(extra.name, 'en')}: up to {extra.max_qty}.")
        if extra.one_per_vehicle and quantity < units:
            raise QuoteError(
                "extra_per_vehicle", f"{_text(extra.name, 'en')}: choose one for each vehicle."
            )
        free = min(quantity, extra.free_qty)
        if free:
            label = f"{name} ({'cortesía' if es else 'complimentary'})"
            lines.append(_line(ItemType.EXTRA, code, label, free, 0))
        if quantity > free:
            price = int(extra.vehicle_prices.get(vehicle.code, extra.price_cents))
            lines.append(_line(ItemType.EXTRA, code, name, quantity - free, price))

    settings = await session.get(CompanySettings, company_id)
    if settings and vehicle.extra_hour_cents:
        hours = sum(
            night_hours(
                leg.service_time, settings.night_surcharge_start, settings.night_surcharge_end
            )
            for leg in request.legs
        )
        if hours:
            label = "Recargo nocturno (por hora)" if es else "Night surcharge (per hour)"
            lines.append(
                _line(ItemType.EXTRA, "NIGHT_SURCHARGE", label, hours, vehicle.extra_hour_cents)
            )

    subtotal = sum(line.total_cents for line in lines)
    promotion, discount = await _promotion(
        session, request.promo_code, request.legs[0].service_date, today, base, subtotal
    )
    if promotion and discount:
        lines.append(
            _line(
                ItemType.DISCOUNT,
                promotion.code,
                _text(promotion.name, request.language),
                1,
                -discount,
            )
        )

    tax_percent = settings.card_tax_percent if settings else 0
    taxed = request.payment == "card" and not departure_only
    tax = ((subtotal - discount) * tax_percent + 50) // 100 if taxed else 0
    total = subtotal - discount + tax
    company = await session.get(Company, company_id)
    applied = promotion if promotion and discount else None
    quote = Quote(
        currency=company.currency if company else "USD",
        lines=lines,
        subtotal_cents=subtotal,
        discount_cents=discount,
        tax_cents=tax,
        total_cents=total,
        vehicle_class=vehicle.code,
        vehicle_count=units,
        zone=zone_slug,
        promotion=_text(applied.name, request.language) if applied else None,
        deposit_cents=min(vehicle.cash_deposit_cents, total) if request.payment == "cash" else 0,
    )
    quote._promotion_id = applied.id if applied else None
    return quote


async def quote_activity(session: AsyncSession, request: ActivityQuoteRequest) -> Quote:
    company = await session.get(Company, _company_id(session))
    package = await session.scalar(
        select(ActivityPackage).where(
            ActivityPackage.slug == request.package, ActivityPackage.is_active
        )
    )
    if package is None:
        raise QuoteError("package_not_found", "We could not find that package.")
    if len(set(request.activities)) != len(request.activities):
        raise QuoteError("duplicate_activities", "Choose different activities.")
    if len(request.activities) != package.activity_count:
        raise QuoteError(
            "activity_count", f"This package includes {package.activity_count} activities."
        )
    activities = (
        await session.scalars(
            select(Activity).where(and_(Activity.slug.in_(request.activities), Activity.is_active))
        )
    ).all()
    if len(activities) != len(request.activities):
        raise QuoteError("activity_not_found", "One of the activities is not available.")

    names = ", ".join(_text(a.name, request.language) for a in activities)
    total = package.price_per_person_cents * request.guests
    return Quote(
        currency=company.currency if company else "USD",
        lines=[
            _line(
                ItemType.ACTIVITY,
                package.slug,
                f"{_text(package.name, request.language)}: {names}",
                request.guests,
                package.price_per_person_cents,
            )
        ],
        subtotal_cents=total,
        discount_cents=0,
        tax_cents=0,
        total_cents=total,
        due_on_site_cents=package.park_fee_cents * request.guests,
        deposit_cents=package.deposit_cents,
    )
