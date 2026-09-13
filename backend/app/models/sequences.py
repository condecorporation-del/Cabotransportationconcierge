import uuid

from sqlalchemy import CheckConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class BookingCodeCounter(Base):
    """Último número de reserva emitido por empresa y año (WORKPLAN F1.11, E7)."""

    __tablename__ = "booking_code_counters"
    __table_args__ = (CheckConstraint("last_value >= 1", name="last_value"),)

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True
    )
    year: Mapped[int] = mapped_column(primary_key=True)
    last_value: Mapped[int]
