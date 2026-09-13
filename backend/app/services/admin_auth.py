"""Login del admin con Argon2id y TOTP obligatorio para owner/manager (WORKPLAN F6.1, F6.2).

Dos pasos cuando el rol exige TOTP: `login()` valida la contraseña y devuelve un
`challenge_token` (firmado, 5 min) en vez de sesión; `verify_totp()` lo cambia por
sesión real. El secreto de un TOTP nuevo viaja dentro de ese token y no se guarda
en la base hasta que el primer código lo confirma, así un QR nunca escaneado no dejó
nada a medias en la cuenta.
"""

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import pyotp
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import (
    admin_totp_challenge_token,
    hash_token,
    read_admin_totp_challenge_token,
    verify_password,
)
from app.models import AdminRole, AdminSession, AdminUser, AuditActor, AuditLog

MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15
SESSION_HOURS = 12
SESSION_COOKIE_NAME = "ctc_admin_session"
CSRF_COOKIE_NAME = "ctc_admin_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
BACKUP_CODE_COUNT = 8
TOTP_ISSUER = "Cabo Transportation Concierge"
TOTP_REQUIRED_ROLES = frozenset({AdminRole.OWNER, AdminRole.MANAGER})

LoginOutcomeKind = Literal["authenticated", "totp_required", "totp_setup_required"]


class InvalidCredentials(AppError):
    status_code = 401

    def __init__(self) -> None:
        super().__init__("invalid_credentials", "Incorrect email or password.")


class AccountLocked(AppError):
    status_code = 423

    def __init__(self) -> None:
        super().__init__("account_locked", "Too many failed attempts. Try again in a few minutes.")


class InvalidTotpCode(AppError):
    status_code = 401

    def __init__(self) -> None:
        super().__init__("invalid_totp_code", "That code is not valid.")


@dataclass
class LoginOutcome:
    kind: LoginOutcomeKind
    admin: AdminUser
    challenge_token: str | None = None
    totp_uri: str | None = None
    session_token: str | None = None
    csrf_token: str | None = None
    backup_codes: list[str] | None = None


async def _find_admin(session: AsyncSession, email: str) -> AdminUser | None:
    admin = await session.scalar(
        select(AdminUser).where(func.lower(AdminUser.email) == email.strip().lower())
    )
    return admin


def _audit(session: AsyncSession, admin: AdminUser, action: str, ip: str | None) -> None:
    session.add(
        AuditLog(
            actor=AuditActor.ADMIN,
            admin_user_id=admin.id,
            action=action,
            entity="admin_user",
            entity_id=admin.id,
            ip=ip,
        )
    )


async def _create_session(
    session: AsyncSession, admin: AdminUser, ip: str | None, user_agent: str | None
) -> tuple[str, str]:
    raw_token = secrets.token_urlsafe(32)
    raw_csrf = secrets.token_urlsafe(32)
    session.add(
        AdminSession(
            admin_user_id=admin.id,
            token_hash=hash_token(raw_token),
            csrf_hash=hash_token(raw_csrf),
            ip=ip,
            user_agent=user_agent[:300] if user_agent else None,
            expires_at=datetime.now(UTC) + timedelta(hours=SESSION_HOURS),
        )
    )
    await session.flush()
    return raw_token, raw_csrf


def _generate_backup_codes() -> list[str]:
    return [
        f"{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}"
        for _ in range(BACKUP_CODE_COUNT)
    ]


def _consume_backup_code(admin: AdminUser, code: str) -> bool:
    hashed = hash_token(code.strip().upper())
    if hashed not in admin.totp_backup_codes:
        return False
    admin.totp_backup_codes = [c for c in admin.totp_backup_codes if c != hashed]
    return True


async def login(
    session: AsyncSession, email: str, password: str, ip: str | None, user_agent: str | None
) -> LoginOutcome:
    """El 6.º intento fallido ya no llega a `verify_password`: lo bloquea `locked_until`."""
    admin = await _find_admin(session, email)
    if admin is None or not admin.is_active:
        raise InvalidCredentials()
    now = datetime.now(UTC)
    if admin.locked_until is not None and admin.locked_until > now:
        raise AccountLocked()
    if not verify_password(password, admin.password_hash):
        admin.failed_logins += 1
        if admin.failed_logins >= MAX_FAILED_LOGINS:
            admin.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
        _audit(session, admin, "login_failed", ip)
        raise InvalidCredentials()

    admin.failed_logins = 0
    admin.locked_until = None
    admin.last_login_at = now

    if admin.role in TOTP_REQUIRED_ROLES:
        if admin.totp_secret is None:
            secret = pyotp.random_base32()
            uri = pyotp.totp.TOTP(secret).provisioning_uri(
                name=admin.email, issuer_name=TOTP_ISSUER
            )
            _audit(session, admin, "login_totp_setup_required", ip)
            return LoginOutcome(
                "totp_setup_required",
                admin,
                challenge_token=admin_totp_challenge_token(admin.id, secret),
                totp_uri=uri,
            )
        _audit(session, admin, "login_totp_required", ip)
        return LoginOutcome(
            "totp_required", admin, challenge_token=admin_totp_challenge_token(admin.id)
        )

    session_token, csrf_token = await _create_session(session, admin, ip, user_agent)
    _audit(session, admin, "login_success", ip)
    return LoginOutcome("authenticated", admin, session_token=session_token, csrf_token=csrf_token)


async def verify_totp(
    session: AsyncSession,
    challenge_token: str,
    code: str,
    ip: str | None,
    user_agent: str | None,
) -> LoginOutcome:
    decoded = read_admin_totp_challenge_token(challenge_token)
    if decoded is None:
        raise InvalidTotpCode()
    admin_id, new_secret = decoded
    admin = await session.get(AdminUser, admin_id)
    if admin is None or not admin.is_active:
        raise InvalidTotpCode()

    if new_secret is not None:
        if not pyotp.totp.TOTP(new_secret).verify(code, valid_window=1):
            raise InvalidTotpCode()
        admin.totp_secret = new_secret
        backup_codes = _generate_backup_codes()
        admin.totp_backup_codes = [hash_token(c) for c in backup_codes]
        session_token, csrf_token = await _create_session(session, admin, ip, user_agent)
        _audit(session, admin, "totp_enrolled", ip)
        return LoginOutcome(
            "authenticated",
            admin,
            session_token=session_token,
            csrf_token=csrf_token,
            backup_codes=backup_codes,
        )

    valid = (
        admin.totp_secret is not None
        and pyotp.totp.TOTP(admin.totp_secret).verify(code, valid_window=1)
    ) or _consume_backup_code(admin, code)
    if not valid:
        _audit(session, admin, "login_totp_failed", ip)
        raise InvalidTotpCode()
    session_token, csrf_token = await _create_session(session, admin, ip, user_agent)
    _audit(session, admin, "login_success", ip)
    return LoginOutcome("authenticated", admin, session_token=session_token, csrf_token=csrf_token)


async def session_for_token(session: AsyncSession, raw_token: str) -> AdminSession | None:
    now = datetime.now(UTC)
    admin_session = await session.scalar(
        select(AdminSession).where(
            AdminSession.token_hash == hash_token(raw_token),
            AdminSession.revoked_at.is_(None),
            AdminSession.expires_at > now,
        )
    )
    return admin_session


def revoke(admin_session: AdminSession) -> None:
    if admin_session.revoked_at is None:
        admin_session.revoked_at = datetime.now(UTC)
