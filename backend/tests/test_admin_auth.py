import pyotp
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, read_admin_totp_challenge_token
from app.models import AdminRole, AdminUser

URL = "/api/v1/admin/auth"
PASSWORD = "Sup3rSecret!23"


async def _admin(
    db: AsyncSession,
    *,
    role: AdminRole = AdminRole.DISPATCHER,
    email: str = "admin@example.com",
    password: str = PASSWORD,
) -> AdminUser:
    admin = AdminUser(email=email, password_hash=hash_password(password), role=role)
    db.add(admin)
    await db.flush()
    return admin


def _totp_secret(challenge_token: str) -> str:
    decoded = read_admin_totp_challenge_token(challenge_token)
    assert decoded is not None
    _, secret = decoded
    assert secret is not None
    return secret


def _csrf_headers(api: AsyncClient) -> dict[str, str]:
    token = api.cookies.get("ctc_admin_csrf")
    assert token is not None
    return {"X-CSRF-Token": token}


async def _logout(api: AsyncClient) -> None:
    await api.post(URL + "/logout", headers=_csrf_headers(api))


async def test_login_without_totp_role_returns_session_cookie(
    api: AsyncClient, db: AsyncSession
) -> None:
    await _admin(db, role=AdminRole.DISPATCHER)
    response = await api.post(
        URL + "/login", json={"email": "admin@example.com", "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "authenticated"
    assert body["csrf_token"]
    assert "ctc_admin_session" in response.cookies


async def test_wrong_password_is_a_generic_invalid_credentials_error(
    api: AsyncClient, db: AsyncSession
) -> None:
    await _admin(db)
    response = await api.post(
        URL + "/login", json={"email": "admin@example.com", "password": "nope"}
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_credentials"


async def test_unknown_email_is_the_same_generic_error(api: AsyncClient, db: AsyncSession) -> None:
    response = await api.post(
        URL + "/login", json={"email": "ghost@example.com", "password": PASSWORD}
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_credentials"


async def test_sixth_failed_attempt_is_locked_out(api: AsyncClient, db: AsyncSession) -> None:
    """Criterio de F6.1: el 6.º intento fallido ya no valida la contraseña, responde bloqueado."""
    await _admin(db)
    wrong = {"email": "admin@example.com", "password": "nope"}
    for _ in range(5):
        response = await api.post(URL + "/login", json=wrong)
        assert response.status_code == 401

    sixth = await api.post(URL + "/login", json=wrong)
    assert sixth.status_code == 423
    assert sixth.json()["detail"]["code"] == "account_locked"

    even_with_the_right_password = await api.post(
        URL + "/login", json={"email": "admin@example.com", "password": PASSWORD}
    )
    assert even_with_the_right_password.status_code == 423


async def test_owner_without_totp_gets_setup_required(api: AsyncClient, db: AsyncSession) -> None:
    await _admin(db, role=AdminRole.OWNER)
    response = await api.post(
        URL + "/login", json={"email": "admin@example.com", "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "totp_setup_required"
    assert body["totp_uri"].startswith("otpauth://totp/")
    assert body["challenge_token"]
    assert "ctc_admin_session" not in response.cookies


async def test_totp_enrollment_completes_login_and_issues_backup_codes(
    api: AsyncClient, db: AsyncSession
) -> None:
    await _admin(db, role=AdminRole.OWNER)
    login = (
        await api.post(URL + "/login", json={"email": "admin@example.com", "password": PASSWORD})
    ).json()
    secret = _totp_secret(login["challenge_token"])
    code = pyotp.TOTP(secret).now()

    response = await api.post(
        URL + "/totp/verify", json={"challenge_token": login["challenge_token"], "code": code}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "authenticated"
    assert len(body["backup_codes"]) == 8
    assert "ctc_admin_session" in response.cookies


async def test_second_login_of_an_enrolled_owner_asks_for_totp_only(
    api: AsyncClient, db: AsyncSession
) -> None:
    await _admin(db, role=AdminRole.OWNER)
    first = (
        await api.post(URL + "/login", json={"email": "admin@example.com", "password": PASSWORD})
    ).json()
    secret = _totp_secret(first["challenge_token"])
    await api.post(
        URL + "/totp/verify",
        json={"challenge_token": first["challenge_token"], "code": pyotp.TOTP(secret).now()},
    )
    await _logout(api)

    second = (
        await api.post(URL + "/login", json={"email": "admin@example.com", "password": PASSWORD})
    ).json()
    assert second["outcome"] == "totp_required"
    decoded = read_admin_totp_challenge_token(second["challenge_token"])
    assert decoded is not None
    assert decoded[1] is None

    verify = await api.post(
        URL + "/totp/verify",
        json={"challenge_token": second["challenge_token"], "code": pyotp.TOTP(secret).now()},
    )
    assert verify.status_code == 200, verify.text
    assert verify.json()["outcome"] == "authenticated"


async def test_wrong_totp_code_is_rejected(api: AsyncClient, db: AsyncSession) -> None:
    await _admin(db, role=AdminRole.OWNER)
    login = (
        await api.post(URL + "/login", json={"email": "admin@example.com", "password": PASSWORD})
    ).json()
    response = await api.post(
        URL + "/totp/verify", json={"challenge_token": login["challenge_token"], "code": "000000"}
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_totp_code"


async def test_backup_code_logs_in_once_and_then_is_rejected(
    api: AsyncClient, db: AsyncSession
) -> None:
    await _admin(db, role=AdminRole.MANAGER)
    login = (
        await api.post(URL + "/login", json={"email": "admin@example.com", "password": PASSWORD})
    ).json()
    secret = _totp_secret(login["challenge_token"])
    enrolled = (
        await api.post(
            URL + "/totp/verify",
            json={"challenge_token": login["challenge_token"], "code": pyotp.TOTP(secret).now()},
        )
    ).json()
    backup_code = enrolled["backup_codes"][0]
    await _logout(api)

    second = (
        await api.post(URL + "/login", json={"email": "admin@example.com", "password": PASSWORD})
    ).json()
    first_use = await api.post(
        URL + "/totp/verify",
        json={"challenge_token": second["challenge_token"], "code": backup_code},
    )
    assert first_use.status_code == 200, first_use.text
    await _logout(api)

    third = (
        await api.post(URL + "/login", json={"email": "admin@example.com", "password": PASSWORD})
    ).json()
    second_use = await api.post(
        URL + "/totp/verify",
        json={"challenge_token": third["challenge_token"], "code": backup_code},
    )
    assert second_use.status_code == 401


async def test_me_requires_a_valid_session_cookie(api: AsyncClient, db: AsyncSession) -> None:
    anonymous = await api.get(URL + "/me")
    assert anonymous.status_code == 401

    await _admin(db, role=AdminRole.DISPATCHER)
    await api.post(URL + "/login", json={"email": "admin@example.com", "password": PASSWORD})
    me = await api.get(URL + "/me")
    assert me.status_code == 200, me.text
    assert me.json() == {"email": "admin@example.com", "role": "dispatcher"}


async def test_logout_revokes_the_session(api: AsyncClient, db: AsyncSession) -> None:
    await _admin(db, role=AdminRole.DISPATCHER)
    await api.post(URL + "/login", json={"email": "admin@example.com", "password": PASSWORD})
    assert (await api.get(URL + "/me")).status_code == 200

    logout = await api.post(URL + "/logout", headers=_csrf_headers(api))
    assert logout.status_code == 204
    assert (await api.get(URL + "/me")).status_code == 401
