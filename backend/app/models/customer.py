from sqlalchemy import Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, IdMixin, TimestampMixin
from app.tenancy import TenantMixin


class Customer(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "customers"
    __table_args__ = (
        Index("uq_customers_company_email", "company_id", text("lower(email)"), unique=True),
    )

    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(30))
    language: Mapped[str] = mapped_column(String(2), default="en")
    country: Mapped[str | None] = mapped_column(String(2))
    marketing_opt_in: Mapped[bool] = mapped_column(default=False)
