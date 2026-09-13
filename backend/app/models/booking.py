"""Reservas con tramos en tabla propia (WORKPLAN D11) y precios congelados por ítem."""

import enum
import uuid
from datetime import date, datetime, time
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, IdMixin, TimestampMixin
from app.tenancy import TenantMixin


class BookingStatus(enum.StrEnum):
    PENDING_PAYMENT = "pending_payment"
    OFFLINE_HOLD = "offline_hold"
    CONFIRMED = "confirmed"
    PAID = "paid"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class BookingSource(enum.StrEnum):
    WEBSITE = "website"
    ADMIN = "admin"
    AI_CHAT = "ai_chat"
    WHATSAPP = "whatsapp"
    PHONE = "phone"


class BookingType(enum.StrEnum):
    TRANSFER = "transfer"
    ACTIVITY = "activity"
    MIXED = "mixed"


class LegType(enum.StrEnum):
    ARRIVAL = "arrival"
    DEPARTURE = "departure"
    LOCAL = "local"


class LegStatus(enum.StrEnum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ItemType(enum.StrEnum):
    TRANSFER = "transfer"
    EXTRA = "extra"
    ACTIVITY = "activity"
    PARK_FEE = "park_fee"
    DISCOUNT = "discount"


class Booking(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "bookings"
    __table_args__ = (
        UniqueConstraint("company_id", "code"),
        CheckConstraint(
            "subtotal_cents >= 0 AND discount_cents >= 0 AND tax_cents >= 0 "
            "AND total_cents = subtotal_cents - discount_cents + tax_cents AND total_cents >= 0 "
            "AND deposit_cents >= 0",
            name="totals",
        ),
        # Listado del admin: todos los estados, filtrables, más recientes primero (WORKPLAN E1).
        Index("ix_bookings_company_status_created", "company_id", "status", "created_at"),
        Index(
            "uq_bookings_company_idempotency_key",
            "company_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    code: Mapped[str] = mapped_column(String(20))
    status: Mapped[BookingStatus]
    source: Mapped[BookingSource]
    booking_type: Mapped[BookingType]
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"), index=True
    )
    language: Mapped[str] = mapped_column(String(2), default="en")
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    subtotal_cents: Mapped[int]
    discount_cents: Mapped[int] = mapped_column(default=0)
    tax_cents: Mapped[int] = mapped_column(default=0)
    total_cents: Mapped[int]
    # Vehículo premium en efectivo (F3.13) o depósito de actividad; se cobra aparte por Stripe.
    deposit_cents: Mapped[int] = mapped_column(default=0, server_default="0")
    promotion_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("promotions.id", ondelete="SET NULL")
    )
    notes_customer: Mapped[str | None] = mapped_column(Text)
    notes_internal: Mapped[str | None] = mapped_column(Text)
    created_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL")
    )
    utm: Mapped[dict[str, Any]] = mapped_column(default=dict)
    cancelled_at: Mapped[datetime | None]
    cancel_reason: Mapped[str | None] = mapped_column(String(300))
    deleted_at: Mapped[datetime | None]
    # Header `Idempotency-Key` de la web: reintentar el POST no duplica la reserva (F3.1).
    idempotency_key: Mapped[str | None] = mapped_column(String(80))
    # F3.12: versión de las políticas que aceptó el cliente; la fecha es created_at.
    terms_version: Mapped[str | None] = mapped_column(String(20))
    # F3.13: "card" o "cash"; solo traslados (WhatsApp decide el método en otros orígenes).
    payment_method: Mapped[str | None] = mapped_column(String(10))

    # raise_on_sql: cargar tramos o ítems exige selectinload explícito (evita N+1 silenciosos).
    # passive_deletes: al borrar, Postgres aplica ON DELETE CASCADE sin cargar los hijos.
    legs: Mapped[list["BookingLeg"]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="raise_on_sql",
        order_by="BookingLeg.service_date",
    )
    items: Mapped[list["BookingItem"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True, lazy="raise_on_sql"
    )


class BookingLeg(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "booking_legs"
    __table_args__ = (
        CheckConstraint("pax_adults >= 1 AND pax_children >= 0", name="pax"),
        # Tablero de despacho por día.
        Index("ix_booking_legs_company_service_date", "company_id", "service_date"),
    )

    booking_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"), index=True
    )
    leg_type: Mapped[LegType]
    status: Mapped[LegStatus] = mapped_column(default=LegStatus.SCHEDULED)
    service_date: Mapped[date]
    service_time: Mapped[time | None]
    pickup_time: Mapped[time | None]
    flight_number: Mapped[str | None] = mapped_column(String(10))
    airline: Mapped[str | None] = mapped_column(String(60))
    origin: Mapped[str] = mapped_column(String(200))
    destination: Mapped[str] = mapped_column(String(200))
    hotel_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("hotels.id", ondelete="SET NULL"))
    pax_adults: Mapped[int]
    pax_children: Mapped[int] = mapped_column(default=0)
    vehicle_class_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vehicle_classes.id", ondelete="RESTRICT")
    )
    # Unidades del mismo vehículo cuando el grupo no cabe en una (F2.11).
    vehicle_count: Mapped[int] = mapped_column(default=1, server_default="1")


class BookingItem(IdMixin, TenantMixin, TimestampMixin, Base):
    """Línea con precio congelado: si luego cambia la tarifa, la reserva no cambia (F2.8)."""

    __tablename__ = "booking_items"
    __table_args__ = (
        CheckConstraint(
            "quantity >= 1 AND total_cents = quantity * unit_price_cents "
            "AND (item_type = 'discount' OR unit_price_cents >= 0)",
            name="amounts",
        ),
    )

    booking_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"), index=True
    )
    leg_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("booking_legs.id", ondelete="CASCADE")
    )
    item_type: Mapped[ItemType]
    # Fecha de la actividad; los traslados la llevan en sus tramos.
    service_date: Mapped[date | None]
    ref_id: Mapped[uuid.UUID | None]
    description: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[int] = mapped_column(default=1)
    unit_price_cents: Mapped[int]
    total_cents: Mapped[int]
