import json

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.turnstile import CaptchaError, verify_turnstile
from app.models import ContactMessage

URL = "/api/v1/contact"
MESSAGE = {"name": "Ana López", "email": "ana@example.com", "message": "Do you have car seats?"}
PRODUCTION = Settings(
    _env_file=None,
    environment="production",
    database_url="postgresql+asyncpg://app:secret@db.example.com:5432/ctc",
    secret_key="k" * 32,
    turnstile_secret_key="turnstile-secret",
    stripe_secret_key="sk_live_x",
    stripe_webhook_secret="whsec_x",
    resend_api_key="re_live_x",
    email_ops_to="ops@cabotransportationconcierge.com",
)


async def test_message_is_saved(api: AsyncClient, db: AsyncSession) -> None:
    response = await api.post(URL, json=MESSAGE | {"source_page": "/contact"})
    assert response.status_code == 202, response.text
    [saved] = (await db.scalars(select(ContactMessage))).all()
    assert (saved.email, saved.source_page) == ("ana@example.com", "/contact")


async def test_bot_filling_the_honeypot_gets_the_same_reply(
    api: AsyncClient, db: AsyncSession
) -> None:
    response = await api.post(URL, json=MESSAGE | {"website": "https://spam.example"})
    assert response.status_code == 202
    assert await db.scalar(select(func.count()).select_from(ContactMessage)) == 0


async def test_configured_turnstile_requires_a_token(
    api: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "turnstile-secret")
    get_settings.cache_clear()
    response = await api.post(URL, json=MESSAGE)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "captcha_required"
    assert await db.scalar(select(func.count()).select_from(ContactMessage)) == 0


def _cloudflare(success: bool, seen: list[dict[str, str]]) -> httpx.AsyncClient:
    def reply(request: httpx.Request) -> httpx.Response:
        seen.append(dict(httpx.QueryParams(request.content.decode())))
        return httpx.Response(200, content=json.dumps({"success": success}))

    return httpx.AsyncClient(transport=httpx.MockTransport(reply))


async def test_production_turnstile_is_verified_with_cloudflare() -> None:
    with pytest.raises(CaptchaError) as missing:
        await verify_turnstile(None, "203.0.113.9", PRODUCTION)
    assert (missing.value.status_code, missing.value.code) == (400, "captcha_required")

    seen: list[dict[str, str]] = []
    await verify_turnstile("token-ok", "203.0.113.9", PRODUCTION, _cloudflare(True, seen))
    assert seen == [
        {"secret": "turnstile-secret", "response": "token-ok", "remoteip": "203.0.113.9"}
    ]
    with pytest.raises(CaptchaError, match="Verification failed"):
        await verify_turnstile("token-bad", None, PRODUCTION, _cloudflare(False, seen))
