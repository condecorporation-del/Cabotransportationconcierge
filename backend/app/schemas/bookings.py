from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import BookingStatus, ItemType
from app.schemas.quotes import ActivityQuoteRequest, TransferQuoteRequest, _Strict


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


class BookingItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    item_type: ItemType
    description: str
    quantity: int
    unit_price_cents: int
    total_cents: int


class BookingCreated(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    status: BookingStatus
    currency: str
    subtotal_cents: int
    discount_cents: int
    tax_cents: int
    total_cents: int
    items: list[BookingItemOut]
