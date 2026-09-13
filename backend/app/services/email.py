"""Cola de correos (D7, F5.2): la API solo encola aquí; `app/worker/send_emails.py` envía.

`grep -rL enqueue backend/app/services/resend_gateway.py backend/app/worker` confirma que
Resend solo se llama desde el worker.
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EmailOutbox


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
