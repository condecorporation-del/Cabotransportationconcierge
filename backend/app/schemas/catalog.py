"""Catálogo público. Los textos van en ambos idiomas para que la respuesta sea cacheable."""

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models import PricingMode, ServiceScope, TripType

I18n = dict[str, str]


class _FromOrm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CompanyOut(_FromOrm):
    """Lo que el sitio necesita del `company_settings` de la empresa (F7.5).

    Deliberadamente parcial: `email_ops` y `email_from` son direcciones internas y no salen
    de aquí. Si mañana se agrega una columna sensible a `company_settings`, no se publica sola
    — hay que nombrarla aquí. El nombre de la empresa no viene de la API: el sitio ya lo sabe.
    """

    phone: str | None
    whatsapp: str | None
    offices: dict[str, Any]
    social_links: dict[str, Any]
    cancellation_hours: int
    change_hours: int
    policies: dict[str, Any]


class ZoneOut(_FromOrm):
    slug: str
    name: I18n
    drive_minutes_min: int
    drive_minutes_max: int
    from_price_cents: int | None = None


class HotelMatch(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    zone: str
    zone_name: I18n


class RateOut(BaseModel):
    vehicle_class: str
    trip_type: TripType
    service_scope: ServiceScope
    price_cents: int


class HotelPage(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    zone: ZoneOut
    rates: list[RateOut]


class VehicleOut(_FromOrm):
    code: str
    name: str
    min_pax: int
    max_pax: int
    max_bags: int
    included_pax: int | None
    extra_pax_cents: int
    extra_hour_cents: int
    cash_deposit_cents: int


class ExtraOut(_FromOrm):
    code: str
    name: I18n
    description: I18n
    price_cents: int
    pricing_mode: PricingMode
    max_qty: int
    included: bool
    free_qty: int
    vehicle_prices: dict[str, int]
    one_per_vehicle: bool


class ActivityOut(_FromOrm):
    slug: str
    name: I18n
    description: I18n
    duration_minutes: int


class PackageOut(_FromOrm):
    slug: str
    name: I18n
    activity_count: int
    price_per_person_cents: int
    park_fee_cents: int
    deposit_cents: int
