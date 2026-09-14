"""Sesión, CSRF y roles del admin (F6.1, F6.3). El resto de rutas de /admin importan de aquí."""

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from app.api.deps import CurrentCompany, DbSession
from app.core.security import hash_token
from app.models import AdminRole, AdminSession, AdminUser
from app.services.admin_auth import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    SESSION_COOKIE_NAME,
    session_for_token,
)

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


async def current_admin_session(
    request: Request,
    _company: CurrentCompany,
    session: DbSession,
) -> AdminSession:
    """`_company` ya fijó `session.info["company_id"]`: el resto de queries quedan filtradas."""
    raw_token = request.cookies.get(SESSION_COOKIE_NAME)
    admin_session = await session_for_token(session, raw_token) if raw_token else None
    if admin_session is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired or invalid.")
    return admin_session


CurrentAdminSession = Annotated[AdminSession, Depends(current_admin_session)]


async def current_admin(admin_session: CurrentAdminSession, session: DbSession) -> AdminUser:
    admin = await session.get(AdminUser, admin_session.admin_user_id)
    if admin is None or not admin.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired or invalid.")
    return admin


CurrentAdmin = Annotated[AdminUser, Depends(current_admin)]


async def require_csrf(request: Request, admin_session: CurrentAdminSession) -> None:
    """Doble token en cada mutación: cookie legible y header deben coincidir entre sí y con el
    hash de la sesión, así una página ajena no puede falsificar el header (no puede leer la cookie).
    """
    if request.method in SAFE_METHODS:
        return
    header = request.headers.get(CSRF_HEADER_NAME)
    cookie = request.cookies.get(CSRF_COOKIE_NAME)
    valid = (
        header is not None and header == cookie and hash_token(header) == admin_session.csrf_hash
    )
    if not valid:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing or invalid CSRF token.")


def require_role(*roles: AdminRole) -> Callable[[AdminUser], Awaitable[AdminUser]]:
    async def check(admin: CurrentAdmin) -> AdminUser:
        if admin.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role can't do this.")
        return admin

    return check


# Ver es cualquier rol; mutar, cualquiera menos viewer (F6.5). Compartido entre routers de /admin.
CAN_EDIT = require_role(AdminRole.OWNER, AdminRole.MANAGER, AdminRole.DISPATCHER, AdminRole.FINANCE)
