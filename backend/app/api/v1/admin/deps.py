"""Sesión del admin desde la cookie (F6.1). El resto de rutas de /admin importan `CurrentAdmin`."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.api.deps import CurrentCompany, DbSession
from app.models import AdminUser
from app.services.admin_auth import SESSION_COOKIE_NAME, admin_from_session_token


async def current_admin(
    request: Request,
    _company: CurrentCompany,
    session: DbSession,
) -> AdminUser:
    """`_company` ya fijó `session.info["company_id"]`: el resto de queries quedan filtradas."""
    raw_token = request.cookies.get(SESSION_COOKIE_NAME)
    admin = await admin_from_session_token(session, raw_token) if raw_token else None
    if admin is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired or invalid.")
    return admin


CurrentAdmin = Annotated[AdminUser, Depends(current_admin)]
