"""Cola de correos (D7, F5.2): la API solo encola aquí; `app/worker/send_emails.py` envía.

`grep -rL enqueue backend/app/services/resend_gateway.py backend/app/worker` confirma que
Resend solo se llama desde el worker.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EmailOutbox, EmailStatus

# F5.11: los únicos dos eventos de Resend que cambian el estado del correo.
RESEND_EVENT_STATUS = {
    "email.delivered": EmailStatus.DELIVERED,
    "email.bounced": EmailStatus.BOUNCED,
}


async def enqueue(
    session: AsyncSession,
    company_id: uuid.UUID,
    template: str,
    to: list[str],
    context: dict[str, Any],
    language: str = "en",
    booking_id: uuid.UUID | None = None,
) -> None:
    session.add(
        EmailOutbox(
            company_id=company_id,
            to_addresses=to,
            template=template,
            language=language,
            context=context,
            booking_id=booking_id,
        )
    )


async def apply_resend_event(session: AsyncSession, event: dict[str, Any]) -> None:
    """F5.11: sin tabla de eventos propia — poner el mismo estado dos veces no hace nada distinto,
    a diferencia de `stripe_events` (F4.4), que evita repetir una *transición*."""
    new_status = RESEND_EVENT_STATUS.get(event.get("type", ""))
    message_id = (event.get("data") or {}).get("email_id")
    if new_status is None or not message_id:
        return
    email = await session.scalar(
        select(EmailOutbox).where(EmailOutbox.provider_message_id == message_id)
    )
    if email is not None:
        email.status = new_status
