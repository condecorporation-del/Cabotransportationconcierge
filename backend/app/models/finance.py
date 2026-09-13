"""Pagos, eventos de Stripe y cuentas por cobrar (WORKPLAN §6). Montos en centavos."""

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, IdMixin, TimestampMixin
from app.tenancy import TenantMixin


class PaymentProvider(enum.StrEnum):
    STRIPE = "stripe"
    CASH = "cash"
    BANK_TRANSFER = "bank_transfer"
    ACCOUNT = "account"
    MANUAL = "manual"


class PaymentStatus(enum.StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"
    CANCELLED = "cancelled"


class AccountStatus(enum.StrEnum):
    OPEN = "open"
    ON_HOLD = "on_hold"
    SETTLED = "settled"
    CLOSED = "closed"


class ChargeStatus(enum.StrEnum):
    PENDING = "pending"
    INVOICED = "invoiced"
    PAID = "paid"
    VOID = "void"


class AccountPaymentMethod(enum.StrEnum):
    CASH = "cash"
    BANK_TRANSFER = "bank_transfer"
    CARD = "card"
    MANUAL = "manual"


class Payment(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(
            "amount_cents > 0 AND refunded_cents >= 0 AND refunded_cents <= amount_cents",
            name="amounts",
        ),
    )

    # RESTRICT: una reserva con pagos no se puede borrar físicamente.
    booking_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bookings.id", ondelete="RESTRICT"), index=True
    )
    provider: Mapped[PaymentProvider]
    status: Mapped[PaymentStatus]
    amount_cents: Mapped[int]
    refunded_cents: Mapped[int] = mapped_column(default=0)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    # Únicos: un intent o checkout de Stripe nunca genera dos pagos (WORKPLAN E9).
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(String(80), unique=True)
    reference: Mapped[str | None] = mapped_column(String(120))
    received_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL")
    )
    paid_at: Mapped[datetime | None]


class StripeEvent(Base):
    """Idempotencia del webhook: el id del evento de Stripe es la llave primaria.

    Sin empresa: el webhook llega antes de saber a qué empresa pertenece el evento.
    """

    __tablename__ = "stripe_events"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    type: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict[str, Any]]
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())
    processed_at: Mapped[datetime | None]


class ClientAccount(IdMixin, TenantMixin, TimestampMixin, Base):
    """Crédito para clientes frecuentes. El saldo se calcula de cargos y abonos, no se guarda."""

    __tablename__ = "client_accounts"
    __table_args__ = (CheckConstraint("credit_limit_cents >= 0", name="credit_limit"),)

    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[AccountStatus] = mapped_column(default=AccountStatus.OPEN)
    credit_limit_cents: Mapped[int] = mapped_column(default=0)


class AccountCharge(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "account_charges"
    __table_args__ = (CheckConstraint("amount_cents > 0", name="amount_positive"),)

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("client_accounts.id", ondelete="CASCADE"), index=True
    )
    booking_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("bookings.id", ondelete="SET NULL")
    )
    description: Mapped[str] = mapped_column(String(200))
    amount_cents: Mapped[int]
    status: Mapped[ChargeStatus] = mapped_column(default=ChargeStatus.PENDING)


class AccountPayment(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "account_payments"
    __table_args__ = (CheckConstraint("amount_cents > 0", name="amount_positive"),)

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("client_accounts.id", ondelete="CASCADE"), index=True
    )
    method: Mapped[AccountPaymentMethod]
    amount_cents: Mapped[int]
    reference: Mapped[str | None] = mapped_column(String(120))
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())
    received_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("admin_users.id", ondelete="SET NULL")
    )
