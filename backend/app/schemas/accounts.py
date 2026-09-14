"""Cuentas por cobrar: crédito, cargos, abonos y ledger (WORKPLAN F6.8)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import AccountPaymentMethod, AccountStatus, ChargeStatus
from app.schemas.quotes import _Strict


class ClientAccountIn(_Strict):
    customer_id: uuid.UUID
    name: str = Field(min_length=1, max_length=120)
    credit_limit_cents: int = Field(default=0, ge=0)


class ClientAccountPatch(_Strict):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    status: AccountStatus | None = None
    credit_limit_cents: int | None = Field(default=None, ge=0)


class ClientAccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    name: str
    status: AccountStatus
    credit_limit_cents: int


class AccountChargeIn(_Strict):
    description: str = Field(min_length=1, max_length=200)
    amount_cents: int = Field(gt=0)


class AccountChargePatch(_Strict):
    description: str | None = Field(default=None, min_length=1, max_length=200)
    amount_cents: int | None = Field(default=None, gt=0)
    status: ChargeStatus | None = None


class AccountChargeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    booking_id: uuid.UUID | None
    description: str
    amount_cents: int
    status: ChargeStatus
    created_at: datetime


class AccountPaymentIn(_Strict):
    method: AccountPaymentMethod
    amount_cents: int = Field(gt=0)
    reference: str | None = Field(default=None, max_length=120)


class AccountPaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    method: AccountPaymentMethod
    amount_cents: int
    reference: str | None
    received_at: datetime


class LinkBookingIn(_Strict):
    booking_id: uuid.UUID


class ClientAccountDetail(ClientAccountOut):
    balance_cents: int
    charges: list[AccountChargeOut]
    payments: list[AccountPaymentOut]
