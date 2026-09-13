"""deposito de la reserva para el pago con stripe

Revision ID: 0e5b48905a6c
Revises: 0d1e992bc78d
Create Date: 2026-09-13 02:13:10.867990
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0e5b48905a6c"
down_revision: str | None = "0d1e992bc78d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bookings", sa.Column("deposit_cents", sa.Integer(), server_default="0", nullable=False)
    )
    # Autogenerate no detecta cambios de CHECK; se agrega deposit_cents >= 0 a mano.
    op.drop_constraint(op.f("ck_bookings_totals"), "bookings", type_="check")
    op.create_check_constraint(
        "totals",
        "bookings",
        "subtotal_cents >= 0 AND discount_cents >= 0 AND tax_cents >= 0 "
        "AND total_cents = subtotal_cents - discount_cents + tax_cents AND total_cents >= 0 "
        "AND deposit_cents >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_bookings_totals"), "bookings", type_="check")
    op.create_check_constraint(
        "totals",
        "bookings",
        "subtotal_cents >= 0 AND discount_cents >= 0 AND tax_cents >= 0 "
        "AND total_cents = subtotal_cents - discount_cents + tax_cents AND total_cents >= 0",
    )
    op.drop_column("bookings", "deposit_cents")
