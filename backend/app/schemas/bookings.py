from datetime import date, time
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models import BookingStatus, ItemType, LegType
from app.schemas.quotes import ActivityQuoteRequest, FlightNumber, TransferQuoteRequest, _Strict


class CustomerIn(_Strict):
    first_name: str = Field(min_length=1, max_length=60)
    last_name: str = Field(min_length=1, max_length=60)
    email: EmailStr = Field(max_length=254)
    confirm_email: EmailStr = Field(max_length=254)
    # Como la referencia: el teléfono es obligatorio, no solo el email.
    phone: str = Field(min_length=7, max_length=30)
    country: str | None = Field(default=None, pattern="^[A-Z]{2}$")
    marketing_opt_in: bool = False

    @model_validator(mode="after")
    def _emails_match(self) -> Self:
        if self.email.lower() != self.confirm_email.lower():
            raise ValueError("Emails don't match")
        return self

    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class Attribution(_Strict):
    """Origen de la visita (F3.11): UTM y referrer que la web captura al entrar."""

    utm_source: str | None = Field(default=None, max_length=100)
    utm_medium: str | None = Field(default=None, max_length=100)
    utm_campaign: str | None = Field(default=None, max_length=100)
    utm_term: str | None = Field(default=None, max_length=100)
    utm_content: str | None = Field(default=None, max_length=100)
    referrer: str | None = Field(default=None, max_length=500)


class _BookingFields(_Strict):
    customer: CustomerIn
    notes: str | None = Field(default=None, max_length=1000)
    attribution: Attribution = Field(default_factory=Attribution)
    # F3.12: debe coincidir con company_settings.terms_version vigente al reservar.
    accepted_terms_version: str = Field(min_length=1, max_length=20)


class TransferBookingRequest(TransferQuoteRequest, _BookingFields):
    @model_validator(mode="after")
    def _public_payment_only(self) -> Self:
        # "stripe", "none" y "account" solo existen en la reserva manual del admin (F6.6).
        if self.payment not in ("card", "cash"):
            raise ValueError("Choose card or cash.")
        return self


class ActivityBookingRequest(ActivityQuoteRequest, _BookingFields):
    pass


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


class PaymentIntentOut(BaseModel):
    """Va al Payment Element de Stripe en el navegador; no es sensible por sí solo."""

    client_secret: str


class PaymentConfirmIn(_Strict):
    payment_intent_id: str = Field(min_length=1, max_length=255)


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
    payment_method: str | None
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
