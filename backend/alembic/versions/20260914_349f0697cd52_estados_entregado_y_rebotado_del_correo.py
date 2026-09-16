"""estados_entregado_y_rebotado_del_correo

Revision ID: 349f0697cd52
Revises: a525576ffab7
Create Date: 2026-09-14 01:14:29.693056
"""

from collections.abc import Sequence

from alembic import op

revision: str = "349f0697cd52"
down_revision: str | None = "a525576ffab7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


OLD = "'pending', 'sending', 'sent', 'failed'"
NEW = "'pending', 'sending', 'sent', 'failed', 'delivered', 'bounced'"


def upgrade() -> None:
    # Autogenerate no detecta cambios de CHECK: hay que rehacerlo a mano (misma lección de
    # F4.2, migración 0e5b48905a6c).
    op.drop_constraint(op.f("ck_email_outbox_emailstatus"), "email_outbox", type_="check")
    op.create_check_constraint("emailstatus", "email_outbox", f"status IN ({NEW})")


def downgrade() -> None:
    op.drop_constraint(op.f("ck_email_outbox_emailstatus"), "email_outbox", type_="check")
    op.create_check_constraint("emailstatus", "email_outbox", f"status IN ({OLD})")
