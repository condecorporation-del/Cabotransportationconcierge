"""Contraseñas con Argon2id, enlaces firmados del cliente y tokens del admin (WORKPLAN §11)."""

import hashlib
import uuid

from itsdangerous import BadSignature, URLSafeTimedSerializer
from pwdlib import PasswordHash

from app.core.config import get_settings

MIN_PASSWORD_LENGTH = 12
BOOKING_TOKEN_SECONDS = 90 * 24 * 3600

_hasher = PasswordHash.recommended()


def hash_token(raw: str) -> str:
    """Sesiones y códigos de respaldo del admin (F6.1, F6.2): valores al azar, hash rápido."""
    return hashlib.sha256(raw.encode()).hexdigest()


def hash_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres")
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _hasher.verify(password, password_hash)


def _booking_signer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="booking-manage")


def booking_token(company_id: uuid.UUID, code: str) -> str:
    """Enlace de gestión del cliente: firmado, de una sola reserva y válido 90 días (F3.5)."""
    return _booking_signer().dumps([str(company_id), code])


def booking_manage_url(company_id: uuid.UUID, code: str) -> str:
    """My Trip con el token ya puesto (F5.4-F5.6): lo que llevan los enlaces de los correos."""
    token = booking_token(company_id, code)
    return f"{get_settings().public_web_url}/my-trip?code={code}&token={token}"


def read_booking_token(token: str, company_id: uuid.UUID) -> str | None:
    """Código de la reserva del token; None si fue alterado, expiró o es de otra empresa."""
    try:
        company, code = _booking_signer().loads(token, max_age=BOOKING_TOKEN_SECONDS)
    except (BadSignature, ValueError):
        return None
    return str(code) if company == str(company_id) else None


ADMIN_TOTP_TOKEN_SECONDS = 5 * 60


def _admin_totp_signer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="admin-totp")


def admin_totp_challenge_token(admin_user_id: uuid.UUID, new_secret: str | None = None) -> str:
    """Identifica al admin entre 'contraseña correcta' y 'TOTP correcto' sin dar sesión (F6.1/F6.2).

    `new_secret` va cuando es alta de TOTP (aún no guardado); None cuando ya tiene uno.
    """
    return _admin_totp_signer().dumps([str(admin_user_id), new_secret])


def read_admin_totp_challenge_token(token: str) -> tuple[uuid.UUID, str | None] | None:
    """None si el token fue alterado o pasaron más de 5 minutos desde el login."""
    try:
        raw_id, new_secret = _admin_totp_signer().loads(token, max_age=ADMIN_TOTP_TOKEN_SECONDS)
        return uuid.UUID(raw_id), new_secret
    except (BadSignature, ValueError):
        return None
