"""Correo por HTTP con Resend (D7, F5.1): envoltura fina, sin lógica de negocio.

Igual que `stripe_gateway.py`: solo la llamada HTTP. El worker decide cuándo reintentar.
"""

import base64
import hashlib
import hmac
import json
import time
from typing import Any

import httpx

from app.core.errors import AppError

API_URL = "https://api.resend.com"
SIGNATURE_TOLERANCE_SECONDS = 300


class EmailSendError(Exception):
    """Resend rechazó el envío; el worker la guarda en `last_error` y reintenta."""


class InvalidResendSignature(AppError):
    status_code = 400

    def __init__(self) -> None:
        super().__init__("invalid_signature", "Invalid Resend signature.")


class ResendGateway:
    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(
            base_url=API_URL, headers={"Authorization": f"Bearer {api_key}"}, timeout=10
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def send(
        self, *, from_addr: str, to: list[str], subject: str, html: str, text: str
    ) -> str:
        try:
            response = await self._client.post(
                "/emails",
                json={"from": from_addr, "to": to, "subject": subject, "html": html, "text": text},
            )
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise EmailSendError("Could not reach Resend.") from exc
        if response.is_error:
            raise EmailSendError(str(body.get("message") or "Resend rejected the email."))
        return str(body["id"])


def verify_webhook(
    payload: bytes,
    svix_id: str,
    svix_timestamp: str,
    svix_signature: str,
    secret: str,
    now: float | None = None,
) -> dict[str, Any]:
    """Resend firma sus webhooks con Svix: `{id}.{timestamp}.{payload}` en HMAC-SHA256, la
    llave en base64 detrás de `whsec_` (F5.11)."""
    if not svix_timestamp.lstrip("-").isdigit() or not secret:
        raise InvalidResendSignature
    if abs((now or time.time()) - int(svix_timestamp)) > SIGNATURE_TOLERANCE_SECONDS:
        raise InvalidResendSignature
    key = base64.b64decode(secret.removeprefix("whsec_"))
    signed = f"{svix_id}.{svix_timestamp}.".encode() + payload
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    signatures = [part.split(",", 1)[1] for part in svix_signature.split() if "," in part]
    if not any(hmac.compare_digest(expected, signature) for signature in signatures):
        raise InvalidResendSignature
    event: dict[str, Any] = json.loads(payload)
    return event
