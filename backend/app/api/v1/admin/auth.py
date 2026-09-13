from fastapi import APIRouter, Depends, Request, Response, status

from app.api.deps import CurrentCompany, DbSession, client_ip
from app.api.v1.admin.deps import CurrentAdmin
from app.core.config import get_settings
from app.core.rate_limit import rate_limit
from app.schemas.admin_auth import AdminMeOut, AuthOut, LoginIn, TotpVerifyIn
from app.services.admin_auth import (
    SESSION_COOKIE_NAME,
    SESSION_HOURS,
    LoginOutcome,
    login,
    revoke_session,
    verify_totp,
)

router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=SESSION_HOURS * 3600,
        httponly=True,
        secure=get_settings().environment not in ("development", "test"),
        samesite="lax",
        path="/",
    )


def _outcome_to_response(outcome: LoginOutcome, response: Response) -> AuthOut:
    if outcome.session_token:
        _set_session_cookie(response, outcome.session_token)
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


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout_route(
    _company: CurrentCompany, session: DbSession, request: Request, response: Response
) -> None:
    raw_token = request.cookies.get(SESSION_COOKIE_NAME)
    if raw_token:
        await revoke_session(session, raw_token)
        await session.commit()
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")


@router.get("/me")
async def me_route(admin: CurrentAdmin) -> AdminMeOut:
    return AdminMeOut(email=admin.email, role=admin.role.value)
