"""Correo por HTTP con Resend (D7, F5.1): envoltura fina, sin lógica de negocio.

Igual que `stripe_gateway.py`: solo la llamada HTTP. El worker decide cuándo reintentar.
"""

import httpx

API_URL = "https://api.resend.com"


class EmailSendError(Exception):
    """Resend rechazó el envío; el worker la guarda en `last_error` y reintenta."""


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
