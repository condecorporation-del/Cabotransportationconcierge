"""Stripe por HTTP (F4.1): envoltura fina, sin lógica de negocio. En tests se simula con respx.

Sin el SDK oficial: tres llamadas y la firma del webhook caben en unas líneas con httpx.
"""

import hashlib
import hmac
import json
import time
from typing import Any

import httpx

from app.core.errors import AppError

API_URL = "https://api.stripe.com/v1"
SIGNATURE_TOLERANCE_SECONDS = 300


class StripeError(AppError):
    status_code = 502


class InvalidSignature(AppError):
    status_code = 400

    def __init__(self) -> None:
        super().__init__("invalid_signature", "Invalid Stripe signature.")


def _form(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    """Formato de Stripe: {"metadata": {"a": 1}} → {"metadata[a]": "1"}; listas van por índice
    ({"line_items": [{"quantity": 1}]} → {"line_items[0][quantity]": "1"}, para Checkout)."""
    form: dict[str, str] = {}
    for key, value in data.items():
        name = f"{prefix}[{key}]" if prefix else key
        if isinstance(value, dict):
            form |= _form(value, name)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                item_name = f"{name}[{index}]"
                form |= _form(item, item_name) if isinstance(item, dict) else {item_name: str(item)}
        elif isinstance(value, bool):
            form[name] = str(value).lower()
        elif value is not None:
            form[name] = str(value)
    return form


class StripeGateway:
    def __init__(self, secret_key: str, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(
            base_url=API_URL, auth=(secret_key, ""), timeout=10
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        data: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
        try:
            response = await self._client.request(
                method, path, data=_form(data or {}), headers=headers
            )
            body: dict[str, Any] = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise StripeError(
                "stripe_unavailable", "Payments are temporarily unavailable. Try again."
            ) from exc
        if response.is_error:
            message = body.get("error", {}).get("message") or "The payment could not be processed."
            raise StripeError("stripe_error", message)
        return body

    async def create_payment_intent(
        self,
        *,
        amount_cents: int,
        currency: str,
        metadata: dict[str, str],
        idempotency_key: str,
        receipt_email: str | None = None,
    ) -> dict[str, Any]:
        data = {
            "amount": amount_cents,
            "currency": currency.lower(),
            "automatic_payment_methods": {"enabled": True},
            "metadata": metadata,
            "receipt_email": receipt_email,
        }
        return await self._request("POST", "/payment_intents", data, idempotency_key)

    async def retrieve_payment_intent(self, intent_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/payment_intents/{intent_id}")

    async def create_refund(
        self, *, payment_intent: str, amount_cents: int | None, idempotency_key: str
    ) -> dict[str, Any]:
        data = {"payment_intent": payment_intent, "amount": amount_cents}
        return await self._request("POST", "/refunds", data, idempotency_key)

    async def create_checkout_session(
        self,
        *,
        amount_cents: int,
        currency: str,
        description: str,
        success_url: str,
        cancel_url: str,
        expires_at: int,
        metadata: dict[str, str],
        idempotency_key: str,
    ) -> dict[str, Any]:
        """F4.6: link real de pago (24 h) para una reserva pendiente."""
        data = {
            "mode": "payment",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "expires_at": expires_at,
            "metadata": metadata,
            "line_items": [
                {
                    "quantity": 1,
                    "price_data": {
                        "currency": currency.lower(),
                        "unit_amount": amount_cents,
                        "product_data": {"name": description},
                    },
                }
            ],
        }
        return await self._request("POST", "/checkout/sessions", data, idempotency_key)

    async def retrieve_checkout_session(self, session_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/checkout/sessions/{session_id}")


def verify_webhook(
    payload: bytes, signature_header: str, secret: str, now: float | None = None
) -> dict[str, Any]:
    """Evento del webhook si la firma `Stripe-Signature` es válida y reciente (5 min)."""
    pairs = [item.split("=", 1) for item in signature_header.split(",") if "=" in item]
    timestamp = next((value for key, value in pairs if key == "t"), "")
    signatures = [value for key, value in pairs if key == "v1"]
    if not timestamp.isdigit() or not secret:
        raise InvalidSignature
    if abs((now or time.time()) - int(timestamp)) > SIGNATURE_TOLERANCE_SECONDS:
        raise InvalidSignature
    signed = f"{timestamp}.".encode() + payload
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, signature) for signature in signatures):
        raise InvalidSignature
    event: dict[str, Any] = json.loads(payload)
    return event
