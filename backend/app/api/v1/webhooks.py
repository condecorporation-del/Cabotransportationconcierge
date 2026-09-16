from typing import Annotated

from fastapi import APIRouter, Header, Request, status
from sqlalchemy.dialects.postgresql import insert

from app.api.deps import DbSession
from app.core.config import get_settings
from app.models import StripeEvent
from app.services.email import apply_resend_event
from app.services.payments import handle_stripe_event
from app.services.resend_gateway import verify_webhook as verify_resend_webhook
from app.services.stripe_gateway import verify_webhook

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request, session: DbSession, stripe_signature: Annotated[str, Header()]
) -> dict[str, str]:
    """Firma inválida → 400 (F4.4). Un evento repetido no se procesa dos veces."""
    # El cuerpo crudo, sin volver a serializar: la firma es sobre esos bytes exactos.
    body = await request.body()
    event = verify_webhook(body, stripe_signature, get_settings().stripe_webhook_secret)
    inserted = await session.execute(
        insert(StripeEvent)
        .values(id=event["id"], type=event["type"], payload=event)
        .on_conflict_do_nothing()
        .returning(StripeEvent.id)
    )
    if inserted.first() is not None:
        await handle_stripe_event(session, event)
    await session.commit()
    return {"status": "ok"}


@router.post("/resend", status_code=status.HTTP_200_OK)
async def resend_webhook(
    request: Request,
    session: DbSession,
    svix_id: Annotated[str, Header()],
    svix_timestamp: Annotated[str, Header()],
    svix_signature: Annotated[str, Header()],
) -> dict[str, str]:
    """Entregado o rebotado actualiza `email_outbox.status` (F5.11); firma inválida → 400."""
    body = await request.body()
    event = verify_resend_webhook(
        body, svix_id, svix_timestamp, svix_signature, get_settings().resend_webhook_secret
    )
    await apply_resend_event(session, event)
    await session.commit()
    return {"status": "ok"}
