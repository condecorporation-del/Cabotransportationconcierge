"""Worker de correos (D7, F5.1): toma la cola con FOR UPDATE SKIP LOCKED, envía y reintenta.

La API solo encola (`app/services/email.py`); un correo caído nunca bloquea una reserva.

uv run python -m app.worker.send_emails            # procesa lo pendiente una vez y sale
uv run python -m app.worker.send_emails --loop      # se queda corriendo (producción)
"""

import argparse
import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.db import engine_from_url
from app.models import EmailOutbox, EmailStatus
from app.services.resend_gateway import EmailSendError, ResendGateway
from app.templates.emails import render

MAX_ATTEMPTS = 5
# Minutos antes del siguiente intento, según cuántos ya fallaron.
BACKOFF_MINUTES = (1, 5, 15, 60, 240)
BATCH_SIZE = 20


async def _send_one(email: EmailOutbox, gateway: ResendGateway) -> None:
    settings = get_settings()
    subject, html, text = render(email.template, email.language, email.context)
    try:
        message_id = await gateway.send(
            from_addr=settings.email_from,
            to=email.to_addresses,
            subject=subject,
            html=html,
            text=text,
        )
    except EmailSendError as exc:
        email.attempts += 1
        email.last_error = str(exc)[:1000]
        if email.attempts >= MAX_ATTEMPTS:
            email.status = EmailStatus.FAILED
        else:
            delay = BACKOFF_MINUTES[min(email.attempts - 1, len(BACKOFF_MINUTES) - 1)]
            email.next_attempt_at = datetime.now(UTC) + timedelta(minutes=delay)
            email.status = EmailStatus.PENDING
        return
    email.status = EmailStatus.SENT
    email.provider_message_id = message_id
    email.sent_at = datetime.now(UTC)


async def run_once(session: AsyncSession, gateway: ResendGateway) -> int:
    """Un lote bloqueado para que dos workers no manden el mismo correo dos veces."""
    rows = (
        (
            await session.execute(
                select(EmailOutbox)
                .where(
                    EmailOutbox.status == EmailStatus.PENDING,
                    EmailOutbox.next_attempt_at <= datetime.now(UTC),
                )
                .order_by(EmailOutbox.next_attempt_at)
                .limit(BATCH_SIZE)
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    for email in rows:
        email.status = EmailStatus.SENDING
        await session.flush()
        await _send_one(email, gateway)
        await session.commit()
    return len(rows)


async def _main(loop: bool) -> None:
    settings = get_settings()
    engine = engine_from_url(settings.database_url, pooled=False)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    gateway = ResendGateway(settings.resend_api_key)
    try:
        while True:
            async with sessionmaker() as session:
                processed = await run_once(session, gateway)
            if not loop:
                break
            await asyncio.sleep(5 if processed else 15)
    finally:
        await gateway.aclose()
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--loop", action="store_true", help="corre indefinidamente (producción)")
    asyncio.run(_main(parser.parse_args().loop))
