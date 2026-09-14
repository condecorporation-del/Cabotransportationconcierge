"""Tablero de despacho (F6.7)."""

import uuid
from datetime import datetime, time
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.quotes import _Strict


class DispatchAssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    unit_index: int
    driver_id: uuid.UUID | None
    driver_name: str | None
    vehicle_id: uuid.UUID | None
    vehicle_plate: str | None
    notified_at: datetime | None


class DispatchLegOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    leg_id: uuid.UUID
    booking_code: str
    leg_type: str
    pickup_time: time | None
    origin: str
    destination: str
    pax_adults: int
    pax_children: int
    vehicle_class_code: str
    vehicle_count: int
    assignments: list[DispatchAssignmentOut]


class AssignIn(_Strict):
    unit_index: int = Field(default=1, ge=1, le=20)
    driver_id: uuid.UUID | None = None
    vehicle_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _needs_one(self) -> Self:
        if self.driver_id is None and self.vehicle_id is None:
            raise ValueError("Choose a driver, a vehicle, or both.")
        return self
