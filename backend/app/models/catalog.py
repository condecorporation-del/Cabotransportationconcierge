"""Catálogo que alimenta el motor de precios (WORKPLAN §6, D8). Montos en centavos."""

import enum
import uuid
from datetime import date
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, IdMixin, TimestampMixin
from app.tenancy import TenantMixin

# Textos bilingües: {"en": "...", "es": "..."}
I18n = dict[str, Any]


class TripType(enum.StrEnum):
    ONE_WAY = "one_way"
    ROUND_TRIP = "round_trip"


class ServiceScope(enum.StrEnum):
    AIRPORT = "airport"
    LOCAL = "local"


class PricingMode(enum.StrEnum):
    PER_BOOKING = "per_booking"
    PER_STOP = "per_stop"
    PER_SEAT = "per_seat"
    PER_HOUR = "per_hour"


class ExtraAutoRule(enum.StrEnum):
    NIGHT_SURCHARGE = "night_surcharge"


class DiscountType(enum.StrEnum):
    PERCENT = "percent"
    FIXED = "fixed"


class PromotionScope(enum.StrEnum):
    TRANSFER_BASE = "transfer_base"
    ALL = "all"


class Zone(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "zones"
    __table_args__ = (UniqueConstraint("company_id", "slug"),)

    slug: Mapped[str] = mapped_column(String(60))
    name: Mapped[I18n]
    sort: Mapped[int] = mapped_column(default=0)
    drive_minutes_min: Mapped[int]
    drive_minutes_max: Mapped[int]
    is_active: Mapped[bool] = mapped_column(default=True)


class Hotel(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "hotels"
    __table_args__ = (
        UniqueConstraint("company_id", "slug"),
        # Búsqueda tolerante a errores (F2.5); requiere la extensión pg_trgm.
        Index(
            "ix_hotels_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )

    zone_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("zones.id", ondelete="RESTRICT"), index=True
    )
    slug: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(160))
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String(160)), default=list)
    is_active: Mapped[bool] = mapped_column(default=True)


class VehicleClass(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "vehicle_classes"
    __table_args__ = (
        UniqueConstraint("company_id", "code"),
        CheckConstraint("min_pax >= 1 AND max_pax >= min_pax", name="pax_range"),
    )

    code: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(80))
    min_pax: Mapped[int] = mapped_column(default=1)
    max_pax: Mapped[int]
    max_bags: Mapped[int]
    sort: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(default=True)


class Rate(IdMixin, TenantMixin, TimestampMixin, Base):
    """Precio por zona, vehículo, tipo de viaje y servicio. Una sola fila por combinación."""

    __tablename__ = "rates"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "zone_id",
            "vehicle_class_id",
            "trip_type",
            "service_scope",
            name="uq_rates_zone_vehicle_trip_scope",
        ),
        CheckConstraint("price_cents >= 0", name="price_non_negative"),
    )

    zone_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("zones.id", ondelete="CASCADE"))
    vehicle_class_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vehicle_classes.id", ondelete="CASCADE")
    )
    trip_type: Mapped[TripType]
    service_scope: Mapped[ServiceScope] = mapped_column(default=ServiceScope.AIRPORT)
    price_cents: Mapped[int]
    is_active: Mapped[bool] = mapped_column(default=True)


class Extra(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "extras"
    __table_args__ = (
        UniqueConstraint("company_id", "code"),
        CheckConstraint("price_cents >= 0 AND max_qty >= 1", name="price_and_qty"),
    )

    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[I18n]
    description: Mapped[I18n] = mapped_column(default=dict)
    price_cents: Mapped[int]
    pricing_mode: Mapped[PricingMode]
    max_qty: Mapped[int] = mapped_column(default=1)
    included: Mapped[bool] = mapped_column(default=False)
    auto_rule: Mapped[ExtraAutoRule | None]
    sort: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(default=True)


class Activity(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "activities"
    __table_args__ = (UniqueConstraint("company_id", "slug"),)

    slug: Mapped[str] = mapped_column(String(60))
    name: Mapped[I18n]
    description: Mapped[I18n] = mapped_column(default=dict)
    duration_minutes: Mapped[int]
    is_active: Mapped[bool] = mapped_column(default=True)


class ActivityPackage(IdMixin, TenantMixin, TimestampMixin, Base):
    """Combos: N actividades por un precio por persona (ClassVIP: 2 por $100, 3 por $125)."""

    __tablename__ = "activity_packages"
    __table_args__ = (
        UniqueConstraint("company_id", "slug"),
        CheckConstraint(
            "activity_count >= 1 AND price_per_person_cents >= 0 "
            "AND park_fee_cents >= 0 AND deposit_cents >= 0",
            name="amounts",
        ),
    )

    slug: Mapped[str] = mapped_column(String(60))
    name: Mapped[I18n]
    activity_count: Mapped[int]
    price_per_person_cents: Mapped[int]
    park_fee_cents: Mapped[int] = mapped_column(default=0)
    deposit_cents: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(default=True)


class Promotion(IdMixin, TenantMixin, TimestampMixin, Base):
    """Sin código = se aplica sola por fechas (ej. SEPTEMBER 10% OFF)."""

    __tablename__ = "promotions"
    __table_args__ = (
        Index(
            "uq_promotions_company_code",
            "company_id",
            text("lower(code)"),
            unique=True,
            postgresql_where=text("code IS NOT NULL"),
        ),
        CheckConstraint(
            "value > 0 AND (discount_type <> 'percent' OR value <= 100)", name="valid_value"
        ),
    )

    code: Mapped[str | None] = mapped_column(String(40))
    name: Mapped[I18n]
    discount_type: Mapped[DiscountType]
    value: Mapped[int]
    applies_to: Mapped[PromotionScope] = mapped_column(default=PromotionScope.TRANSFER_BASE)
    travel_from: Mapped[date | None]
    travel_to: Mapped[date | None]
    book_from: Mapped[date | None]
    book_to: Mapped[date | None]
    max_uses: Mapped[int | None]
    used_count: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(default=True)
