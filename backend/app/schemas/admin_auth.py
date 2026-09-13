from typing import Literal

from pydantic import EmailStr, Field

from app.schemas.quotes import _Strict


class LoginIn(_Strict):
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=1, max_length=200)


class TotpVerifyIn(_Strict):
    challenge_token: str = Field(min_length=10, max_length=2000)
    code: str = Field(min_length=6, max_length=9)


class AuthOut(_Strict):
    """Misma forma para `/login` (roles sin TOTP) y `/totp/verify`."""

    outcome: Literal["authenticated", "totp_required", "totp_setup_required"]
    challenge_token: str | None = None
    totp_uri: str | None = None
    csrf_token: str | None = None
    backup_codes: list[str] | None = None


class AdminMeOut(_Strict):
    email: str
    role: str
