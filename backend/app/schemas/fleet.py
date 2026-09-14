"""Flota: choferes, vehículos y clases de vehículo (WORKPLAN F6.8).

Sin `DELETE`: como el catálogo (`seed_catalog.py`), desactivar (`is_active=False`) es la forma
de retirar uno sin romper reservas, tramos o asignaciones que ya lo referencian.
"""

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.quotes import _Strict


class DriverIn(_Strict):
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=7, max_length=30)
    whatsapp: str | None = Field(default=None, max_length=30)
    # Aviso de tramo asignado (F5.9); sin correo, no se le notifica nada.
    email: EmailStr | None = Field(default=None, max_length=254)
    license_number: str | None = Field(default=None, max_length=40)
    license_expires_on: date | None = None
    languages: list[str] = Field(default_factory=list, max_length=10)
    is_active: bool = True


class DriverPatch(_Strict):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    phone: str | None = Field(default=None, min_length=7, max_length=30)
    whatsapp: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = Field(default=None, max_length=254)
    license_number: str | None = Field(default=None, max_length=40)
    license_expires_on: date | None = None
    languages: list[str] | None = Field(default=None, max_length=10)
    is_active: bool | None = None


class DriverOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    phone: str
    whatsapp: str | None
    email: str | None
    license_number: str | None
    license_expires_on: date | None
    languages: list[str]
    is_active: bool


class VehicleIn(_Strict):
    vehicle_class_id: uuid.UUID
    plate: str = Field(min_length=1, max_length=15)
    make: str = Field(min_length=1, max_length=40)
    model: str = Field(min_length=1, max_length=40)
    year: int | None = Field(default=None, ge=1980, le=2100)
    color: str | None = Field(default=None, max_length=30)
    capacity: int = Field(ge=1)
    insurance_expires_on: date | None = None
    is_active: bool = True


class VehiclePatch(_Strict):
    vehicle_class_id: uuid.UUID | None = None
    plate: str | None = Field(default=None, min_length=1, max_length=15)
    make: str | None = Field(default=None, min_length=1, max_length=40)
    model: str | None = Field(default=None, min_length=1, max_length=40)
    year: int | None = Field(default=None, ge=1980, le=2100)
    color: str | None = Field(default=None, max_length=30)
    capacity: int | None = Field(default=None, ge=1)
    insurance_expires_on: date | None = None
    is_active: bool | None = None


class VehicleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    vehicle_class_id: uuid.UUID
    plate: str
    make: str
    model: str
    year: int | None
    color: str | None
    capacity: int
    insurance_expires_on: date | None
    is_active: bool


class VehicleClassIn(_Strict):
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=80)
    min_pax: int = Field(default=1, ge=1)
    max_pax: int = Field(ge=1)
    max_bags: int = Field(ge=0)
    included_pax: int | None = None
    extra_pax_cents: int = Field(default=0, ge=0)
    extra_hour_cents: int = Field(default=0, ge=0)
    cash_deposit_cents: int = Field(default=0, ge=0)
    sort: int = 0
    is_active: bool = True


class VehicleClassPatch(_Strict):
    code: str | None = Field(default=None, min_length=1, max_length=30)
    name: str | None = Field(default=None, min_length=1, max_length=80)
    min_pax: int | None = Field(default=None, ge=1)
    max_pax: int | None = Field(default=None, ge=1)
    max_bags: int | None = Field(default=None, ge=0)
    included_pax: int | None = None
    extra_pax_cents: int | None = Field(default=None, ge=0)
    extra_hour_cents: int | None = Field(default=None, ge=0)
    cash_deposit_cents: int | None = Field(default=None, ge=0)
    sort: int | None = None
    is_active: bool | None = None


class VehicleClassOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    min_pax: int
    max_pax: int
    max_bags: int
    included_pax: int | None
    extra_pax_cents: int
    extra_hour_cents: int
    cash_deposit_cents: int
    sort: int
    is_active: bool
