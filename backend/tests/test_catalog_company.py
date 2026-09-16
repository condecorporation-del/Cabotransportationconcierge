from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CompanySettings

URL = "/api/v1/catalog/company"


async def test_company_exposes_what_the_site_needs(api: AsyncClient, db: AsyncSession) -> None:
    settings = await db.scalar(select(CompanySettings))
    assert settings is not None
    settings.phone = "+52 (624) 123 4567"
    settings.social_links = {"google_review": "https://g.page/ctc/review"}
    await db.flush()

    body = (await api.get(URL)).json()

    assert body["phone"] == "+52 (624) 123 4567"
    assert body["social_links"]["google_review"] == "https://g.page/ctc/review"
    assert body["cancellation_hours"] == settings.cancellation_hours


async def test_company_never_publishes_the_internal_addresses(api: AsyncClient) -> None:
    # `email_ops` es a dónde llegan los avisos internos y `email_from` el remitente: ninguno
    # de los dos tiene por qué salir en el sitio público.
    body = (await api.get(URL)).json()

    assert "email_ops" not in body
    assert "email_from" not in body
