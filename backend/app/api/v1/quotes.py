from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends

from app.api.deps import CurrentCompany, DbSession
from app.core.rate_limit import rate_limit
from app.schemas.quotes import ActivityQuoteRequest, Quote, QuoteRequest
from app.services.pricing import quote_activity, quote_transfer

router = APIRouter(prefix="/quotes", tags=["quotes"], dependencies=[Depends(rate_limit(60))])


@router.post("")
async def create_quote(body: QuoteRequest, company: CurrentCompany, session: DbSession) -> Quote:
    """Cotización autoritativa; los errores corregibles responden 422 con `code` estable."""
    if isinstance(body, ActivityQuoteRequest):
        return await quote_activity(session, body)
    today = datetime.now(ZoneInfo(company.timezone)).date()
    return await quote_transfer(session, body, today)
