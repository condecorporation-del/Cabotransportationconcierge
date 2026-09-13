import enum
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, IdMixin, TimestampMixin


class AdminRole(enum.StrEnum):
    OWNER = "owner"
    MANAGER = "manager"
    DISPATCHER = "dispatcher"
    FINANCE = "finance"
    VIEWER = "viewer"


class AdminUser(IdMixin, TimestampMixin, Base):
    __tablename__ = "admin_users"
    __table_args__ = (
        # Email único por empresa sin importar mayúsculas.
        Index("uq_admin_users_company_email", "company_id", text("lower(email)"), unique=True),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    email: Mapped[str] = mapped_column(String(254))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[AdminRole]
    is_active: Mapped[bool] = mapped_column(default=True)
    totp_secret: Mapped[str | None] = mapped_column(String(255))
    last_login_at: Mapped[datetime | None]
    failed_logins: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None]


class AdminSession(IdMixin, Base):
    """Sesión de servidor revocable; solo se guardan hashes de los tokens."""

    __tablename__ = "sessions"

    admin_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("admin_users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
