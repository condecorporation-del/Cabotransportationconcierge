"""Contratos de cotización. Los montos siempre salen del servidor (WORKPLAN D8)."""

import re
import uuid
from datetime import date, time
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

from app.models import ItemType, ServiceScope, TripType

Language = Literal["en", "es"]
# Código IATA (2) o ICAO (3) de la aerolínea + número de 1 a 4 dígitos + sufijo opcional.
FLIGHT_NUMBER = re.compile(r"([A-Z]{3}|[A-Z0-9]{2})\d{1,4}[A-Z]?")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LegIn(_Strict):
    service_date: date
    # Hora de aterrizaje en la llegada u hora de pickup en la salida; define el recargo nocturno.
    service_time: time | None = None
    # Solo al reservar; la cotización los ignora.
    flight_number: str | None = Field(default=None, max_length=10)
    airline: str | None = Field(default=None, max_length=60)
    international: bool = True

    @field_validator("flight_number")
    @classmethod
    def _flight_format(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.replace(" ", "").replace("-", "").upper()
        if not FLIGHT_NUMBER.fullmatch(normalized):
            raise ValueError("Use the airline code and flight number, e.g. AA1245")
        return normalized


class ExtraIn(_Strict):
    code: str = Field(min_length=1, max_length=40)
    quantity: int = Field(ge=1, le=20)


class TransferQuoteRequest(_Strict):
    type: Literal["transfer"] = "transfer"
    hotel_id: uuid.UUID
    trip_type: TripType
    service_scope: ServiceScope = ServiceScope.AIRPORT
    passengers: int = Field(ge=1, le=50)
    vehicle_class: str | None = Field(default=None, max_length=30)
    legs: list[LegIn] = Field(min_length=1, max_length=2)
    extras: list[ExtraIn] = Field(default_factory=list, max_length=20)
    promo_code: str | None = Field(default=None, min_length=1, max_length=40)
    language: Language = "en"

    @model_validator(mode="after")
    def _check_legs_and_extras(self) -> Self:
        expected = 2 if self.trip_type is TripType.ROUND_TRIP else 1
        if len(self.legs) != expected:
            raise ValueError(f"{self.trip_type.value} requires {expected} leg(s)")
        if expected == 2:
            arrival, back = self.legs
            same_day_earlier = (
                back.service_date == arrival.service_date
                and back.service_time is not None
                and arrival.service_time is not None
                and back.service_time <= arrival.service_time
            )
            if back.service_date < arrival.service_date or same_day_earlier:
                raise ValueError("The return must be after the arrival")
        if len({extra.code for extra in self.extras}) != len(self.extras):
            raise ValueError("Each extra can appear only once")
        return self


class ActivityQuoteRequest(_Strict):
    type: Literal["activity"] = "activity"
    package: str = Field(min_length=1, max_length=60)
    activities: list[str] = Field(min_length=1, max_length=10)
    guests: int = Field(ge=1, le=30)
    service_date: date
    language: Language = "en"


QuoteRequest = Annotated[TransferQuoteRequest | ActivityQuoteRequest, Field(discriminator="type")]


class QuoteLine(BaseModel):
    kind: ItemType
    code: str | None
    description: str
    quantity: int
    unit_price_cents: int
    total_cents: int


class Quote(BaseModel):
    currency: str
    lines: list[QuoteLine]
    subtotal_cents: int
    discount_cents: int
    tax_cents: int
    total_cents: int
    vehicle_class: str | None = None
    zone: str | None = None
    promotion: str | None = None
    # Actividades: se pagan en sitio (park fee) o se retienen como depósito; no suman al total.
    due_on_site_cents: int = 0
    deposit_cents: int = 0
    # Interno: la reserva guarda qué promoción aplicó; no sale en la respuesta.
    _promotion_id: uuid.UUID | None = PrivateAttr(default=None)
