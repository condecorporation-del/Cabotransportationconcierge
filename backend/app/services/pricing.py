"""Motor único de precios (WORKPLAN D8): web, admin, IA y Stripe cotizan solo aquí.

Reglas (detalle y ejemplos en docs/decisions/ADR-002-precios.md):
- Vehículo automático por pasajeros; se permite subir de clase, nunca bajar.
- Extras una vez por reserva: precio unitario por cantidad, dentro de su máximo.
- Recargo nocturno automático si alguna hora cae en la ventana de la empresa.
- Una sola promoción (la de mayor descuento), evaluada con la fecha del primer tramo.
"""

import uuid
from datetime import date, time
from typing import Any

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.models import (
    Activity,
    ActivityPackage,
    Company,
    CompanySettings,
    DiscountType,
    Extra,
    ExtraAutoRule,
    Hotel,
    ItemType,
    Promotion,
    PromotionScope,
    Rate,
    TripType,
    VehicleClass,
    Zone,
)
from app.schemas.quotes import ActivityQuoteRequest, Quote, QuoteLine, TransferQuoteRequest


class QuoteError(ValueError):
    """Error que el cliente puede corregir; `code` es estable para traducirlo en la web."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def in_night_window(moment: time, start: time, end: time) -> bool:
    """Ventana [start, end); si start > end cruza la medianoche (23:00 a 05:00)."""
    return (moment >= start or moment < end) if start > end else start <= moment < end


def _text(i18n: dict[str, Any], language: str) -> str:
    return str(i18n.get(language) or i18n.get("en") or "")


def _company_id(session: AsyncSession) -> uuid.UUID:
    company_id: uuid.UUID | None = session.info.get("company_id")
    if company_id is None:
        raise RuntimeError("La sesión no tiene empresa (session.info['company_id'])")
    return company_id


async def _vehicle(session: AsyncSession, passengers: int, requested: str | None) -> VehicleClass:
    classes = (
        await session.scalars(
            select(VehicleClass).where(VehicleClass.is_active).order_by(VehicleClass.max_pax)
        )
    ).all()
    if requested:
        chosen = next((v for v in classes if v.code == requested), None)
        if chosen is None:
            raise QuoteError("vehicle_unavailable", f"Vehicle {requested} is not available.")
        if passengers > chosen.max_pax:
            raise QuoteError("vehicle_too_small", f"{chosen.name} fits up to {chosen.max_pax}.")
        return chosen
    chosen = next((v for v in classes if v.min_pax <= passengers <= v.max_pax), None)
    if chosen is None:
        raise QuoteError(
            "too_many_passengers", "This group needs more than one vehicle. Contact us to book it."
        )
    return chosen


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


def _total(lines: list[QuoteLine]) -> int:
    return sum(line.total_cents for line in lines)


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

    vehicle = await _vehicle(session, request.passengers, request.vehicle_class)
    rate = await session.scalar(
        select(Rate).where(
            Rate.zone_id == hotel.zone_id,
            Rate.vehicle_class_id == vehicle.id,
            Rate.trip_type == request.trip_type,
            Rate.service_scope == request.service_scope,
            Rate.is_active,
        )
    )
    if rate is None:
        raise QuoteError("rate_unavailable", "Rate unavailable. Try another vehicle or contact us.")

    trip = "round trip" if request.trip_type is TripType.ROUND_TRIP else "one way"
    lines = [
        QuoteLine(
            kind=ItemType.TRANSFER,
            code=vehicle.code,
            description=f"{vehicle.name}, {trip}",
            quantity=1,
            unit_price_cents=rate.price_cents,
            total_cents=rate.price_cents,
        )
    ]

    requested = {extra.code: extra.quantity for extra in request.extras}
    extras = (
        await session.scalars(
            select(Extra).where(
                Extra.is_active,
                or_(Extra.code.in_(requested), Extra.auto_rule.is_not(None)),
            )
        )
    ).all()
    by_code = {extra.code: extra for extra in extras}
    for code, quantity in requested.items():
        extra = by_code.get(code)
        if extra is None or extra.included or extra.auto_rule is not None:
            raise QuoteError("extra_unavailable", f"The extra {code} is not available.")
        if quantity > extra.max_qty:
            raise QuoteError("extra_quantity", f"{_text(extra.name, 'en')}: up to {extra.max_qty}.")
        lines.append(
            QuoteLine(
                kind=ItemType.EXTRA,
                code=code,
                description=_text(extra.name, request.language),
                quantity=quantity,
                unit_price_cents=extra.price_cents,
                total_cents=extra.price_cents * quantity,
            )
        )

    settings = await session.get(CompanySettings, company_id)
    night = next((e for e in extras if e.auto_rule is ExtraAutoRule.NIGHT_SURCHARGE), None)
    if (
        night
        and settings
        and any(
            leg.service_time
            and in_night_window(
                leg.service_time, settings.night_surcharge_start, settings.night_surcharge_end
            )
            for leg in request.legs
        )
    ):
        lines.append(
            QuoteLine(
                kind=ItemType.EXTRA,
                code=night.code,
                description=_text(night.name, request.language),
                quantity=1,
                unit_price_cents=night.price_cents,
                total_cents=night.price_cents,
            )
        )

    subtotal = _total(lines)
    promotion, discount = await _promotion(
        session,
        request.promo_code,
        request.legs[0].service_date,
        today,
        rate.price_cents,
        subtotal,
    )
    if promotion and discount:
        lines.append(
            QuoteLine(
                kind=ItemType.DISCOUNT,
                code=promotion.code,
                description=_text(promotion.name, request.language),
                quantity=1,
                unit_price_cents=-discount,
                total_cents=-discount,
            )
        )

    company = await session.get(Company, company_id)
    return Quote(
        currency=company.currency if company else "USD",
        lines=lines,
        subtotal_cents=subtotal,
        discount_cents=discount,
        tax_cents=0,
        total_cents=subtotal - discount,
        vehicle_class=vehicle.code,
        zone=zone_slug,
        promotion=_text(promotion.name, request.language) if promotion and discount else None,
    )


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
            QuoteLine(
                kind=ItemType.ACTIVITY,
                code=package.slug,
                description=f"{_text(package.name, request.language)}: {names}",
                quantity=request.guests,
                unit_price_cents=package.price_per_person_cents,
                total_cents=total,
            )
        ],
        subtotal_cents=total,
        discount_cents=0,
        tax_cents=0,
        total_cents=total,
        due_on_site_cents=package.park_fee_cents * request.guests,
        deposit_cents=package.deposit_cents,
    )
