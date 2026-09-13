from fastapi import APIRouter, Depends, Request, Response, status

from app.api.deps import CurrentCompany, DbSession, client_ip
from app.api.v1.admin.deps import CurrentAdmin, CurrentAdminSession, require_csrf
from app.core.config import get_settings
from app.core.rate_limit import rate_limit
from app.schemas.admin_auth import AdminMeOut, AuthOut, LoginIn, TotpVerifyIn
from app.services.admin_auth import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    SESSION_HOURS,
    LoginOutcome,
    login,
    revoke,
    verify_totp,
)

router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])


def _set_admin_cookies(response: Response, session_token: str, csrf_token: str) -> None:
    secure = get_settings().environment not in ("development", "test")
    max_age = SESSION_HOURS * 3600
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_token,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    # Legible por JS a propósito: es la mitad que el header X-CSRF-Token debe repetir (F6.3).
    response.set_cookie(
        CSRF_COOKIE_NAME,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )


def _outcome_to_response(outcome: LoginOutcome, response: Response) -> AuthOut:
    if outcome.session_token and outcome.csrf_token:
        _set_admin_cookies(response, outcome.session_token, outcome.csrf_token)
    return AuthOut(
        outcome=outcome.kind,
        challenge_token=outcome.challenge_token,
        totp_uri=outcome.totp_uri,
        csrf_token=outcome.csrf_token,
        backup_codes=outcome.backup_codes,
    )


@router.post("/login", dependencies=[Depends(rate_limit(10))])
async def login_route(
    body: LoginIn,
    _company: CurrentCompany,
    session: DbSession,
    request: Request,
    response: Response,
) -> AuthOut:
    """Contraseña correcta con owner/manager no entrega sesión: exige TOTP (F6.2)."""
    outcome = await login(
        session, body.email, body.password, client_ip(request), request.headers.get("user-agent")
    )
    await session.commit()
    return _outcome_to_response(outcome, response)


@router.post("/totp/verify", dependencies=[Depends(rate_limit(10))])
async def totp_verify_route(
    body: TotpVerifyIn,
    _company: CurrentCompany,
    session: DbSession,
    request: Request,
    response: Response,
) -> AuthOut:
    """Alta (secreto nuevo en el token) o login normal, según lo que traiga el `challenge_token`."""
    outcome = await verify_totp(
        session,
        body.challenge_token,
        body.code,
        client_ip(request),
        request.headers.get("user-agent"),
    )
    await session.commit()
    return _outcome_to_response(outcome, response)


@router.post(
    "/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_csrf)]
)
async def logout_route(
    admin_session: CurrentAdminSession, session: DbSession, response: Response
) -> None:
    revoke(admin_session)
    await session.commit()
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")


@router.get("/me")
async def me_route(admin: CurrentAdmin) -> AdminMeOut:
    return AdminMeOut(email=admin.email, role=admin.role.value)
