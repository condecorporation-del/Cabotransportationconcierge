from datetime import date, time
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import BookingStatus, ItemType, LegType
from app.schemas.quotes import ActivityQuoteRequest, FlightNumber, TransferQuoteRequest, _Strict


class CustomerIn(_Strict):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr = Field(max_length=254)
    phone: str | None = Field(default=None, max_length=30)
    country: str | None = Field(default=None, pattern="^[A-Z]{2}$")
    marketing_opt_in: bool = False


class TransferBookingRequest(TransferQuoteRequest):
    # Solo para one way: llegada (aeropuerto → hotel) o salida (hotel → aeropuerto).
    direction: Literal["arrival", "departure"] = "arrival"
    customer: CustomerIn
    notes: str | None = Field(default=None, max_length=1000)


class ActivityBookingRequest(ActivityQuoteRequest):
    customer: CustomerIn
    notes: str | None = Field(default=None, max_length=1000)


BookingRequest = Annotated[
    TransferBookingRequest | ActivityBookingRequest, Field(discriminator="type")
]


class _FromOrm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LegChange(_Strict):
    leg_type: LegType
    service_time: time | None = None
    flight_number: FlightNumber | None = None
    airline: str | None = Field(default=None, max_length=60)


class BookingChange(_Strict):
    legs: list[LegChange] = Field(default_factory=list, max_length=2)
    notes: str | None = Field(default=None, max_length=1000)


class CancelRequest(_Strict):
    reason: str | None = Field(default=None, max_length=300)


class BookingItemOut(_FromOrm):
    item_type: ItemType
    service_date: date | None
    description: str
    quantity: int
    unit_price_cents: int
    total_cents: int


class BookingLegOut(_FromOrm):
    leg_type: LegType
    service_date: date
    service_time: time | None
    pickup_time: time | None
    flight_number: str | None
    airline: str | None
    origin: str
    destination: str
    pax_adults: int
    pax_children: int


class BookingSummary(_FromOrm):
    code: str
    status: BookingStatus
    currency: str
    subtotal_cents: int
    discount_cents: int
    tax_cents: int
    total_cents: int
    items: list[BookingItemOut]


class BookingToken(BaseModel):
    """Token de gestión: va en `Authorization: Bearer` para ver o cambiar la reserva."""

    token: str


class BookingCreated(BookingSummary, BookingToken):
    pass


class BookingDetail(BookingSummary):
    legs: list[BookingLegOut]
    notes_customer: str | None
