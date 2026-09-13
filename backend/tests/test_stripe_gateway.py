import hashlib
import hmac
import json
import time
from urllib.parse import parse_qs

import httpx
import pytest
import respx

from app.services.stripe_gateway import (
    API_URL,
    InvalidSignature,
    StripeError,
    StripeGateway,
    verify_webhook,
)

SECRET = "whsec_test"


@respx.mock(base_url=API_URL, assert_all_called=True)
async def test_payment_intent_is_created_with_idempotency(respx_mock: respx.MockRouter) -> None:
    route = respx_mock.post("/payment_intents").respond(
        200, json={"id": "pi_1", "client_secret": "pi_1_secret"}
    )
    gateway = StripeGateway("sk_test_123")
    intent = await gateway.create_payment_intent(
        amount_cents=26500,
        currency="USD",
        metadata={"booking_id": "b1", "company_id": "c1"},
        idempotency_key="intent-b1-26500",
    )
    await gateway.aclose()

    assert intent["client_secret"] == "pi_1_secret"
    request = route.calls.last.request
    assert request.headers["Idempotency-Key"] == "intent-b1-26500"
    assert request.headers["Authorization"].startswith("Basic ")
    assert parse_qs(request.content.decode()) == {
        "amount": ["26500"],
        "currency": ["usd"],
        "automatic_payment_methods[enabled]": ["true"],
        "metadata[booking_id]": ["b1"],
        "metadata[company_id]": ["c1"],
    }


@respx.mock(base_url=API_URL)
async def test_stripe_errors_become_clear_app_errors(respx_mock: respx.MockRouter) -> None:
    respx_mock.get("/payment_intents/pi_bad").respond(
        404, json={"error": {"message": "No such payment_intent: 'pi_bad'"}}
    )
    respx_mock.get("/payment_intents/pi_down").mock(side_effect=httpx.ConnectTimeout("timeout"))
    gateway = StripeGateway("sk_test_123")
    with pytest.raises(StripeError, match="No such payment_intent") as rejected:
        await gateway.retrieve_payment_intent("pi_bad")
    with pytest.raises(StripeError) as down:
        await gateway.retrieve_payment_intent("pi_down")
    await gateway.aclose()
    assert (rejected.value.code, down.value.code) == ("stripe_error", "stripe_unavailable")
    assert down.value.status_code == 502


def _signed(payload: bytes, timestamp: int, secret: str = SECRET) -> str:
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256)
    return f"t={timestamp},v1={digest.hexdigest()}"


def test_webhook_signature_is_verified() -> None:
    payload = json.dumps({"id": "evt_1", "type": "payment_intent.succeeded"}).encode()
    now = int(time.time())
    assert verify_webhook(payload, _signed(payload, now), SECRET)["id"] == "evt_1"

    rejected = [
        (payload.replace(b"evt_1", b"evt_2"), _signed(payload, now)),
        (payload, _signed(payload, now - 301)),
        (payload, _signed(payload, now, secret="whsec_other")),
        (payload, "v1=abc"),
    ]
    for body, header in rejected:
        with pytest.raises(InvalidSignature):
            verify_webhook(body, header, SECRET, now=now)
