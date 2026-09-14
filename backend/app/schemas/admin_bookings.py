"""Listado, detalle y acciones de reservas del admin (F6.4, F6.5, F6.6)."""

import uuid
from datetime import date, datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import (
    AuditActor,
    BookingSource,
    BookingStatus,
    BookingType,
    PaymentProvider,
    PaymentStatus,
)
from app.schemas.bookings import BookingItemOut, BookingLegOut, CustomerIn
from app.schemas.quotes import TransferQuoteRequest, _Strict


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


class AdminManualBookingRequest(TransferQuoteRequest):
    """Alta manual del admin (F6.6): mismo motor de precios, pago sin tarjeta al instante."""

    account_id: uuid.UUID | None = None
    customer: CustomerIn
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _admin_payment_rules(self) -> Self:
        if self.payment not in ("none", "cash", "stripe", "account"):
            raise ValueError("Choose none, cash, stripe or account for a manual booking.")
        if self.payment == "account" and self.account_id is None:
            raise ValueError("account_id is required when payment is 'account'")
        return self
