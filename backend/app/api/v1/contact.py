from fastapi import APIRouter, Depends, Request, status

from app.api.deps import CurrentCompany, DbSession, client_ip
from app.core.config import get_settings
from app.core.rate_limit import rate_limit
from app.core.turnstile import verify_turnstile
from app.models import ContactMessage
from app.schemas.contact import ContactIn, ContactReceived
from app.services.email import enqueue

router = APIRouter(prefix="/contact", tags=["contact"], dependencies=[Depends(rate_limit(5))])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def contact(
    body: ContactIn, company: CurrentCompany, session: DbSession, request: Request
) -> ContactReceived:
    """Formulario de contacto. A un bot (honeypot con texto) se le responde igual sin guardar."""
    if not body.website:
        settings = get_settings()
        await verify_turnstile(body.turnstile_token, client_ip(request), settings)
        session.add(ContactMessage(**body.model_dump(exclude={"website", "turnstile_token"})))
        await enqueue(
            session, company.id, "contact_ack", [body.email], {"name": body.name}, body.language
        )
        if settings.email_ops_to:
            await enqueue(
                session,
                company.id,
                "contact_lead",
                [settings.email_ops_to],
                {"name": body.name, "email": body.email, "message": body.message},
            )
        await session.commit()
    return ContactReceived()
