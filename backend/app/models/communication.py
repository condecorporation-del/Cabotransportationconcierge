"""Cola de correos, conversaciones de IA, mensajes de contacto y reseñas (WORKPLAN §6)."""

import enum
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, SmallInteger, String, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, IdMixin, TimestampMixin
from app.tenancy import TenantMixin


class EmailStatus(enum.StrEnum):
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    # F5.11: los deja el webhook de Resend, nunca el worker.
    DELIVERED = "delivered"
    BOUNCED = "bounced"


class ConversationStatus(enum.StrEnum):
    OPEN = "open"
    HANDOFF = "handoff"
    CLOSED = "closed"


class MessageRole(enum.StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ContactStatus(enum.StrEnum):
    NEW = "new"
    REPLIED = "replied"
    ARCHIVED = "archived"


class ReviewSource(enum.StrEnum):
    GOOGLE = "google"
    TRIPADVISOR = "tripadvisor"


class EmailOutbox(IdMixin, TenantMixin, TimestampMixin, Base):
    """Cola del worker (D7): la API solo encola; el worker envía con reintentos."""

    __tablename__ = "email_outbox"
    __table_args__ = (
        CheckConstraint("attempts >= 0", name="attempts"),
        # Solo los pendientes: el worker los toma por fecha sin recorrer los ya enviados.
        Index(
            "ix_email_outbox_pending_next_attempt",
            "next_attempt_at",
            postgresql_where=text("status = 'pending'"),
        ),
    )

    to_addresses: Mapped[list[str]] = mapped_column(ARRAY(String(254)))
    template: Mapped[str] = mapped_column(String(60))
    language: Mapped[str] = mapped_column(String(2), default="en")
    context: Mapped[dict[str, Any]] = mapped_column(default=dict)
    booking_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("bookings.id", ondelete="SET NULL")
    )
    status: Mapped[EmailStatus] = mapped_column(default=EmailStatus.PENDING)
    attempts: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(server_default=func.now())
    provider_message_id: Mapped[str | None] = mapped_column(String(120))
    last_error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None]


class AiConversation(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "ai_conversations"
    __table_args__ = (Index("ix_ai_conversations_company_created", "company_id", "created_at"),)

    # Visitante anónimo: solo el hash de su token de sesión.
    visitor_token_hash: Mapped[str] = mapped_column(String(64), index=True)
    language: Mapped[str] = mapped_column(String(2), default="en")
    status: Mapped[ConversationStatus] = mapped_column(default=ConversationStatus.OPEN)
    customer_email: Mapped[str | None] = mapped_column(String(254))
    lead_booking_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("bookings.id", ondelete="SET NULL")
    )
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    # Millonésimas de dólar en entero: sin errores de punto flotante al sumar costos.
    cost_micro_usd: Mapped[int] = mapped_column(default=0)


class AiMessage(IdMixin, TenantMixin, Base):
    __tablename__ = "ai_messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[MessageRole]
    content: Mapped[str] = mapped_column(Text)
    tool_name: Mapped[str | None] = mapped_column(String(60))
    tool_payload: Mapped[dict[str, Any] | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ContactMessage(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "contact_messages"
    __table_args__ = (
        Index("ix_contact_messages_company_status_created", "company_id", "status", "created_at"),
    )

    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(30))
    message: Mapped[str] = mapped_column(Text)
    source_page: Mapped[str | None] = mapped_column(String(200))
    language: Mapped[str] = mapped_column(String(2), default="en")
    status: Mapped[ContactStatus] = mapped_column(default=ContactStatus.NEW)


class Review(IdMixin, TenantMixin, TimestampMixin, Base):
    """Solo reseñas reales del cliente, con su enlace de origen (WORKPLAN §10)."""

    __tablename__ = "reviews"
    __table_args__ = (CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range"),)

    author: Mapped[str] = mapped_column(String(120))
    location: Mapped[str | None] = mapped_column(String(120))
    source: Mapped[ReviewSource]
    rating: Mapped[int] = mapped_column(SmallInteger)
    body: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(2), default="en")
    review_date: Mapped[date]
    url: Mapped[str | None] = mapped_column(String(500))
    is_featured: Mapped[bool] = mapped_column(default=False)
