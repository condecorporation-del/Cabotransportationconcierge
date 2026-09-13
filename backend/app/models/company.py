import uuid
from datetime import time
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, IdMixin, TimestampMixin


class Company(IdMixin, TimestampMixin, Base):
    """Empresa (tenant). Todo dato de negocio cuelga de una (WORKPLAN D10)."""

    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(120))
    slug: Mapped[str] = mapped_column(String(60), unique=True)
    legal_name: Mapped[str | None] = mapped_column(String(200))
    tax_id: Mapped[str | None] = mapped_column(String(20))
    timezone: Mapped[str] = mapped_column(String(40), default="America/Mazatlan")
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    default_language: Mapped[str] = mapped_column(String(2), default="en")


class CompanySettings(TimestampMixin, Base):
    """Datos públicos y políticas editables en el admin. Textos bilingües: {"en": …, "es": …}."""

    __tablename__ = "company_settings"

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True
    )
    phone: Mapped[str | None] = mapped_column(String(30))
    whatsapp: Mapped[str | None] = mapped_column(String(30))
    email_ops: Mapped[str | None] = mapped_column(String(254))
    email_from: Mapped[str | None] = mapped_column(String(254))
    offices: Mapped[dict[str, Any]] = mapped_column(default=dict)
    social_links: Mapped[dict[str, Any]] = mapped_column(default=dict)
    cancellation_hours: Mapped[int] = mapped_column(default=24)
    change_hours: Mapped[int] = mapped_column(default=5)
    # Anticipación mínima para reservar en la web (F3.3).
    min_notice_hours: Mapped[int] = mapped_column(default=24, server_default="24")
    night_surcharge_start: Mapped[time] = mapped_column(default=time(23, 0))
    night_surcharge_end: Mapped[time] = mapped_column(default=time(5, 0))
    arrival_instructions: Mapped[dict[str, Any]] = mapped_column(default=dict)
    policies: Mapped[dict[str, Any]] = mapped_column(default=dict)
