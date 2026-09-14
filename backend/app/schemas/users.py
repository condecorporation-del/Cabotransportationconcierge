"""Usuarios y roles del admin, solo el dueño de la empresa (WORKPLAN F6.13)."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.security import MIN_PASSWORD_LENGTH
from app.models import AdminRole, AuditActor
from app.schemas.quotes import _Strict


class AdminUserIn(_Strict):
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=200)
    role: AdminRole


class AdminUserPatch(_Strict):
    role: AdminRole | None = None
    is_active: bool | None = None


class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: AdminRole
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor: AuditActor
    admin_user_id: uuid.UUID | None
    action: str
    entity: str
    entity_id: uuid.UUID | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    ip: str | None
    created_at: datetime


class AuditLogPage(BaseModel):
    items: list[AuditLogOut]
    total: int
    page: int
    page_size: int
