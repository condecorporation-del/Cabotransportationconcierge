from fastapi import APIRouter, Depends, Request, status

from app.api.deps import DbSession, client_ip, get_company
from app.core.config import get_settings
from app.core.rate_limit import rate_limit
from app.core.turnstile import verify_turnstile
from app.models import ContactMessage
from app.schemas.contact import ContactIn, ContactReceived

router = APIRouter(
    prefix="/contact", tags=["contact"], dependencies=[Depends(rate_limit(5)), Depends(get_company)]
)


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def contact(body: ContactIn, session: DbSession, request: Request) -> ContactReceived:
    """Formulario de contacto. A un bot (honeypot con texto) se le responde igual sin guardar."""
    if not body.website:
        await verify_turnstile(body.turnstile_token, client_ip(request), get_settings())
        session.add(ContactMessage(**body.model_dump(exclude={"website", "turnstile_token"})))
        await session.commit()
    return ContactReceived()
