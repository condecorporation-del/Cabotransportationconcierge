import httpx

from app.core.config import Settings
from app.core.errors import AppError

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


class CaptchaError(AppError):
    status_code = 400


async def verify_turnstile(
    token: str | None,
    ip: str | None,
    settings: Settings,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Cloudflare Turnstile en formularios públicos. Sin secreto (solo en local) no se exige."""
    if not settings.turnstile_secret_key:
        return
    if not token:
        raise CaptchaError("captcha_required", "Complete the verification and try again.")
    payload = {"secret": settings.turnstile_secret_key, "response": token, "remoteip": ip or ""}
    try:
        async with client or httpx.AsyncClient(timeout=5) as http:
            response = await http.post(VERIFY_URL, data=payload)
        success = response.is_success and response.json().get("success") is True
    except (httpx.HTTPError, ValueError):
        success = False
    if not success:
        raise CaptchaError("captcha_failed", "Verification failed. Please try again.")
