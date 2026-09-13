"""Flota, despacho, tareas del equipo y auditoría (WORKPLAN §6)."""

import enum
import uuid
from datetime import date, datetime, time
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, IdMixin, TimestampMixin
from app.tenancy import TenantMixin


class TaskCategory(enum.StrEnum):
    VEHICLE_SERVICE = "vehicle_service"
    OPERATION = "operation"
    ADMIN = "admin"
    OTHER = "other"


class TaskStatus(enum.StrEnum):
    PENDING = "pending"
    DONE = "done"
    CANCELLED = "cancelled"


class AuditActor(enum.StrEnum):
    ADMIN = "admin"
    CUSTOMER = "customer"
    SYSTEM = "system"


class Driver(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "drivers"

    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(30))
    whatsapp: Mapped[str | None] = mapped_column(String(30))
    license_number: Mapped[str | None] = mapped_column(String(40))
    license_expires_on: Mapped[date | None]
    languages: Mapped[list[str]] = mapped_column(ARRAY(String(2)), default=list)
    is_active: Mapped[bool] = mapped_column(default=True)


class Vehicle(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "vehicles"
    __table_args__ = (
        UniqueConstraint("company_id", "plate"),
        CheckConstraint("capacity >= 1", name="capacity"),
    )

    vehicle_class_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vehicle_classes.id", ondelete="RESTRICT")
    )
    plate: Mapped[str] = mapped_column(String(15))
    make: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(40))
    year: Mapped[int | None]
    color: Mapped[str | None] = mapped_column(String(30))
    capacity: Mapped[int]
    insurance_expires_on: Mapped[date | None]
    is_active: Mapped[bool] = mapped_column(default=True)


class BookingAssignment(IdMixin, TenantMixin, TimestampMixin, Base):
    """Chofer y vehículo de un tramo. Una sola asignación por tramo."""

    __tablename__ = "booking_assignments"
    __table_args__ = (
        UniqueConstraint("leg_id"),
        CheckConstraint(
            "driver_id IS NOT NULL OR vehicle_id IS NOT NULL", name="driver_or_vehicle"
        ),
    )

    leg_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("booking_legs.id", ondelete="CASCADE"))
    # Índice: detectar choques de horario del mismo chofer al asignar (F6.7).
    driver_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("drivers.id", ondelete="RESTRICT"), index=True
    )
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vehicles.id", ondelete="RESTRICT")
    )
    assigned_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL")
    )
    notified_at: Mapped[datetime | None]


class AdminTask(IdMixin, TenantMixin, TimestampMixin, Base):
    """Tareas compartidas por el equipo (en ClassVIP vivían solo en localStorage)."""

    __tablename__ = "admin_tasks"
    __table_args__ = (
        Index("ix_admin_tasks_company_status_due", "company_id", "status", "due_date"),
    )

    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text)
    due_date: Mapped[date | None]
    due_time: Mapped[time | None]
    category: Mapped[TaskCategory] = mapped_column(default=TaskCategory.OTHER)
    status: Mapped[TaskStatus] = mapped_column(default=TaskStatus.PENDING)
    assigned_to_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL")
    )


class AuditLog(IdMixin, TenantMixin, Base):
    """Quién cambió qué y cuándo, con el antes y el después (se escribe en F6.10)."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_company_entity", "company_id", "entity", "entity_id"),
        Index("ix_audit_logs_company_created", "company_id", "created_at"),
    )

    actor: Mapped[AuditActor]
    admin_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(40))
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[uuid.UUID | None]
    before: Mapped[dict[str, Any] | None]
    after: Mapped[dict[str, Any] | None]
    ip: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
