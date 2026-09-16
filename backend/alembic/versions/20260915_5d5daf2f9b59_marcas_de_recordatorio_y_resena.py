"""marcas_de_recordatorio_y_resena

Revision ID: 5d5daf2f9b59
Revises: 349f0697cd52
Create Date: 2026-09-15 22:40:47.841202
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5d5daf2f9b59"
down_revision: str | None = "349f0697cd52"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # F5.7: por tramo, no por reserva — una ida y vuelta lleva dos recordatorios.
    op.add_column(
        "booking_legs", sa.Column("reminder_sent_at", sa.DateTime(timezone=True), nullable=True)
    )
    # F5.8: por reserva — la reseña se pide una vez por viaje.
    op.add_column(
        "bookings", sa.Column("review_requested_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("bookings", "review_requested_at")
    op.drop_column("booking_legs", "reminder_sent_at")
