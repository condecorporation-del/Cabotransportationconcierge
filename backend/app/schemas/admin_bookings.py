"""Listado, detalle y acciones de reservas del admin (F6.4, F6.5)."""

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import (
    AuditActor,
    BookingSource,
    BookingStatus,
    BookingType,
    PaymentProvider,
    PaymentStatus,
)
from app.schemas.bookings import BookingItemOut, BookingLegOut
from app.schemas.quotes import _Strict


class AdminBookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    status: BookingStatus
    booking_type: BookingType
    source: BookingSource
    payment_method: str | None
    currency: str
    total_cents: int
    service_date: date | None
    created_at: datetime
    customer_name: str
    customer_email: str
    customer_phone: str | None


class AdminBookingPage(BaseModel):
    items: list[AdminBookingOut]
    total: int
    page: int
    page_size: int


class AdminPaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider: PaymentProvider
    status: PaymentStatus
    amount_cents: int
    refunded_cents: int
    currency: str
    paid_at: datetime | None


class AdminBookingDetail(BaseModel):
    id: uuid.UUID
    code: str
    status: BookingStatus
    booking_type: BookingType
    source: BookingSource
    payment_method: str | None
    currency: str
    subtotal_cents: int
    discount_cents: int
    tax_cents: int
    total_cents: int
    deposit_cents: int
    created_at: datetime
    notes_customer: str | None
    notes_internal: str | None
    customer_name: str
    customer_email: str
    customer_phone: str | None
    legs: list[BookingLegOut]
    items: list[BookingItemOut]
    payments: list[AdminPaymentOut]


class TimelineEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    actor: AuditActor
    admin_user_id: uuid.UUID | None
    action: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    ip: str | None
    created_at: datetime


class MarkPaidIn(_Strict):
    provider: Literal["cash", "bank_transfer", "manual", "account"]


class AdminCancelIn(_Strict):
    reason: str | None = Field(default=None, max_length=300)
    refund: bool = False
