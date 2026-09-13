"""Aislamiento por empresa en el ORM (WORKPLAN D10, F1.2).

Con `session.info["company_id"]` definido:
- todo SELECT de modelos con `TenantMixin` se filtra por esa empresa;
- al hacer flush se completa `company_id` faltante y se rechaza escribir filas de otra empresa.
"""

import uuid
from typing import Any

from sqlalchemy import ForeignKey, event
from sqlalchemy.orm import (
    Mapped,
    ORMExecuteState,
    Session,
    mapped_column,
    with_loader_criteria,
)


class CrossTenantWriteError(RuntimeError):
    """Se intentó guardar una fila que pertenece a otra empresa."""


class TenantMixin:
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))


@event.listens_for(Session, "do_orm_execute")
def _filter_by_company(state: ORMExecuteState) -> None:
    company_id = state.session.info.get("company_id")
    if company_id is None or not state.is_select or state.is_column_load:
        return
    state.statement = state.statement.options(
        with_loader_criteria(
            TenantMixin, lambda cls: cls.company_id == company_id, include_aliases=True
        )
    )


@event.listens_for(Session, "before_flush")
def _guard_company_writes(session: Session, _context: Any, _instances: Any) -> None:
    company_id = session.info.get("company_id")
    if company_id is None:
        return
    for obj in (*session.new, *session.dirty):
        if not isinstance(obj, TenantMixin):
            continue
        if obj.company_id is None:
            obj.company_id = company_id
        elif obj.company_id != company_id:
            raise CrossTenantWriteError(f"{type(obj).__name__} pertenece a otra empresa")
