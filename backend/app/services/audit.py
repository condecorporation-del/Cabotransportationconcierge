"""Auditoría automática de ediciones (WORKPLAN F6.10): un evento de sesión, no código repetido
en cada endpoint. `current_admin` (F6.1) deja `session.info["admin_user_id"]`; aquí solo se lee.

Cubre `session.dirty` (una fila que ya existía y cambió) porque el criterio de F6.10 es sobre
editar, no sobre crear: una fila nueva todavía no tiene `id` en `before_flush` (el default de
`IdMixin` se resuelve al armar el INSERT), así que auditar altas automáticamente pediría otro
evento (`after_flush`) con sus propias complicaciones que esta tarea no necesita resolver.
"""

import uuid
from datetime import date, datetime, time
from enum import Enum
from typing import Any

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.models import (
    AccountCharge,
    AccountPayment,
    AdminTask,
    AuditActor,
    AuditLog,
    ClientAccount,
    Driver,
    Vehicle,
    VehicleClass,
)

# Modelos que hoy no arman su propio AuditLog a mano. Las reservas ya tienen una bitácora más
# rica en booking_state.py (actor, motivo); no se duplica aquí.
AUDITED_MODELS = (
    Driver,
    Vehicle,
    VehicleClass,
    AdminTask,
    ClientAccount,
    AccountCharge,
    AccountPayment,
)


def _serialize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    return value


def _diff(obj: Any) -> tuple[dict[str, Any], dict[str, Any]] | None:
    state = inspect(obj)
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for attr in state.mapper.column_attrs:
        history = state.attrs[attr.key].history
        if not history.has_changes():
            continue
        before[attr.key] = _serialize(history.deleted[0]) if history.deleted else None
        after[attr.key] = _serialize(getattr(obj, attr.key))
    return (before, after) if before else None


@event.listens_for(Session, "before_flush")
def _audit_edits(session: Session, _context: Any, _instances: Any) -> None:
    admin_id = session.info.get("admin_user_id")
    for obj in list(session.dirty):
        if not isinstance(obj, AUDITED_MODELS):
            continue
        if not session.is_modified(obj, include_collections=False):
            continue
        diff = _diff(obj)
        if diff is None:
            continue
        before, after = diff
        session.add(
            AuditLog(
                company_id=obj.company_id,
                actor=AuditActor.ADMIN if admin_id else AuditActor.SYSTEM,
                admin_user_id=admin_id,
                action="update",
                entity=obj.__tablename__,
                entity_id=obj.id,
                before=before,
                after=after,
            )
        )
