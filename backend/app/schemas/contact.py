from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.schemas.quotes import Language, _Strict


class ContactIn(_Strict):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr = Field(max_length=254)
    phone: str | None = Field(default=None, max_length=30)
    message: str = Field(min_length=5, max_length=5000)
    source_page: str | None = Field(default=None, max_length=200)
    language: Language = "en"
    # Honeypot: campo invisible para personas; si llega con texto lo envió un bot.
    website: str | None = Field(default=None, max_length=200)
    turnstile_token: str | None = Field(default=None, max_length=2048)


class ContactReceived(BaseModel):
    status: Literal["received"] = "received"
