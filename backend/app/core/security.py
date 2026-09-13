"""Contraseñas con Argon2id (WORKPLAN §11). Nunca se guarda ni se registra la contraseña."""

from pwdlib import PasswordHash

MIN_PASSWORD_LENGTH = 12

_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres")
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _hasher.verify(password, password_hash)
