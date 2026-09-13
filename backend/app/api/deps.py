import hashlib
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, Response, status
from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db import get_session
from app.models import Company

DbSession = Annotated[AsyncSession, Depends(get_session)]


async def get_company(session: DbSession) -> Company:
    """Fija la empresa del request en la sesión; desde aquí todo query queda filtrado (F1.2)."""
    company = await session.scalar(
        select(Company).where(Company.slug == get_settings().default_company_slug)
    )
    if company is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Service not configured.")
    session.info["company_id"] = company.id
    return company


CurrentCompany = Annotated[Company, Depends(get_company)]


def cached_json(request: Request, schema: Any, value: Any) -> Response:
    """JSON con ETag: si el cliente ya tiene esta versión responde 304 sin cuerpo."""
    body = TypeAdapter(schema).dump_json(value)
    etag = f'"{hashlib.blake2b(body, digest_size=16).hexdigest()}"'
    headers = {"ETag": etag, "Cache-Control": "public, max-age=60"}
    if etag in request.headers.get("if-none-match", ""):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return Response(body, media_type="application/json", headers=headers)
