"""Listado de reservas del admin (F6.4)."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models import BookingSource, BookingStatus, BookingType


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
