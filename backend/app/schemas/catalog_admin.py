"""Catálogo CRUD del admin (WORKPLAN F6.12). Sin `DELETE`: `is_active=false` retira una fila
sin romper tarifas, hoteles o extras que ya la referencian (misma convención que F6.8).
"""

import uuid
from datetime import date, time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models import (
    DiscountType,
    ExtraAutoRule,
    PricingMode,
    PromotionScope,
    ServiceScope,
    TripType,
)
from app.schemas.quotes import _Strict

I18n = dict[str, str]


class ZoneIn(_Strict):
    slug: str = Field(min_length=1, max_length=60)
    name: I18n
    sort: int = 0
    drive_minutes_min: int = Field(ge=0)
    drive_minutes_max: int = Field(ge=0)
    is_active: bool = True


class ZonePatch(_Strict):
    slug: str | None = Field(default=None, min_length=1, max_length=60)
    name: I18n | None = None
    sort: int | None = None
    drive_minutes_min: int | None = Field(default=None, ge=0)
    drive_minutes_max: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ZoneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: I18n
    sort: int
    drive_minutes_min: int
    drive_minutes_max: int
    is_active: bool


class HotelIn(_Strict):
    zone_id: uuid.UUID
    slug: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=160)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    is_active: bool = True


class HotelPatch(_Strict):
    zone_id: uuid.UUID | None = None
    slug: str | None = Field(default=None, min_length=1, max_length=120)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    aliases: list[str] | None = Field(default=None, max_length=20)
    is_active: bool | None = None


class HotelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    zone_id: uuid.UUID
    slug: str
    name: str
    aliases: list[str]
    is_active: bool


class RateIn(_Strict):
    zone_id: uuid.UUID
    vehicle_class_id: uuid.UUID
    trip_type: TripType
    service_scope: ServiceScope = ServiceScope.AIRPORT
    price_cents: int = Field(ge=0)
    is_active: bool = True


class RatePatch(_Strict):
    price_cents: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class RateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    zone_id: uuid.UUID
    vehicle_class_id: uuid.UUID
    trip_type: TripType
    service_scope: ServiceScope
    price_cents: int
    is_active: bool


class ExtraIn(_Strict):
    code: str = Field(min_length=1, max_length=40)
    name: I18n
    description: I18n = Field(default_factory=dict)
    price_cents: int = Field(ge=0)
    pricing_mode: PricingMode
    max_qty: int = Field(default=1, ge=1)
    included: bool = False
    free_qty: int = Field(default=0, ge=0)
    vehicle_prices: dict[str, int] = Field(default_factory=dict)
    one_per_vehicle: bool = False
    auto_rule: ExtraAutoRule | None = None
    sort: int = 0
    is_active: bool = True


class ExtraPatch(_Strict):
    name: I18n | None = None
    description: I18n | None = None
    price_cents: int | None = Field(default=None, ge=0)
    pricing_mode: PricingMode | None = None
    max_qty: int | None = Field(default=None, ge=1)
    included: bool | None = None
    free_qty: int | None = Field(default=None, ge=0)
    vehicle_prices: dict[str, int] | None = None
    one_per_vehicle: bool | None = None
    auto_rule: ExtraAutoRule | None = None
    sort: int | None = None
    is_active: bool | None = None


class ExtraOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: I18n
    description: I18n
    price_cents: int
    pricing_mode: PricingMode
    max_qty: int
    included: bool
    free_qty: int
    vehicle_prices: dict[str, Any]
    one_per_vehicle: bool
    auto_rule: ExtraAutoRule | None
    sort: int
    is_active: bool


class ActivityIn(_Strict):
    slug: str = Field(min_length=1, max_length=60)
    name: I18n
    description: I18n = Field(default_factory=dict)
    duration_minutes: int = Field(gt=0)
    is_active: bool = True


class ActivityPatch(_Strict):
    name: I18n | None = None
    description: I18n | None = None
    duration_minutes: int | None = Field(default=None, gt=0)
    is_active: bool | None = None


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: I18n
    description: I18n
    duration_minutes: int
    is_active: bool


class ActivityPackageIn(_Strict):
    slug: str = Field(min_length=1, max_length=60)
    name: I18n
    activity_count: int = Field(ge=1)
    price_per_person_cents: int = Field(ge=0)
    park_fee_cents: int = Field(default=0, ge=0)
    deposit_cents: int = Field(default=0, ge=0)
    is_active: bool = True


class ActivityPackagePatch(_Strict):
    name: I18n | None = None
    activity_count: int | None = Field(default=None, ge=1)
    price_per_person_cents: int | None = Field(default=None, ge=0)
    park_fee_cents: int | None = Field(default=None, ge=0)
    deposit_cents: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ActivityPackageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: I18n
    activity_count: int
    price_per_person_cents: int
    park_fee_cents: int
    deposit_cents: int
    is_active: bool


class PromotionIn(_Strict):
    code: str | None = Field(default=None, min_length=1, max_length=40)
    name: I18n
    discount_type: DiscountType
    value: int = Field(gt=0)
    applies_to: PromotionScope = PromotionScope.TRANSFER_BASE
    travel_from: date | None = None
    travel_to: date | None = None
    book_from: date | None = None
    book_to: date | None = None
    max_uses: int | None = Field(default=None, ge=1)
    is_active: bool = True


class PromotionPatch(_Strict):
    name: I18n | None = None
    discount_type: DiscountType | None = None
    value: int | None = Field(default=None, gt=0)
    applies_to: PromotionScope | None = None
    travel_from: date | None = None
    travel_to: date | None = None
    book_from: date | None = None
    book_to: date | None = None
    max_uses: int | None = Field(default=None, ge=1)
    is_active: bool | None = None


class PromotionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str | None
    name: I18n
    discount_type: DiscountType
    value: int
    applies_to: PromotionScope
    travel_from: date | None
    travel_to: date | None
    book_from: date | None
    book_to: date | None
    max_uses: int | None
    used_count: int
    is_active: bool


class CompanySettingsPatch(_Strict):
    phone: str | None = Field(default=None, max_length=30)
    whatsapp: str | None = Field(default=None, max_length=30)
    email_ops: str | None = Field(default=None, max_length=254)
    email_from: str | None = Field(default=None, max_length=254)
    offices: dict[str, Any] | None = None
    social_links: dict[str, Any] | None = None
    cancellation_hours: int | None = Field(default=None, ge=0)
    change_hours: int | None = Field(default=None, ge=0)
    min_notice_hours: int | None = Field(default=None, ge=0)
    card_tax_percent: int | None = Field(default=None, ge=0, le=100)
    terms_version: str | None = Field(default=None, min_length=1, max_length=20)
    night_surcharge_start: time | None = None
    night_surcharge_end: time | None = None
    arrival_instructions: dict[str, Any] | None = None
    policies: dict[str, Any] | None = None


class CompanySettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    phone: str | None
    whatsapp: str | None
    email_ops: str | None
    email_from: str | None
    offices: dict[str, Any]
    social_links: dict[str, Any]
    cancellation_hours: int
    change_hours: int
    min_notice_hours: int
    card_tax_percent: int
    terms_version: str
    night_surcharge_start: time
    night_surcharge_end: time
    arrival_instructions: dict[str, Any]
    policies: dict[str, Any]
