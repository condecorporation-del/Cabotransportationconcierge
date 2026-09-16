import base64
import hashlib
import hmac
import json
import time

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import EmailOutbox, EmailStatus

SECRET_KEY = b"test-resend-webhook-secret-bytes"
SECRET = "whsec_" + base64.b64encode(SECRET_KEY).decode()
WEBHOOK = "/api/v1/webhooks/resend"


@pytest.fixture(autouse=True)
def _configured_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", SECRET)
    get_settings.cache_clear()


def _headers(payload: bytes, *, svix_id: str = "msg_1", secret: str = SECRET) -> dict[str, str]:
    timestamp = str(int(time.time()))
    key = base64.b64decode(secret.removeprefix("whsec_"))
    signed = f"{svix_id}.{timestamp}.".encode() + payload
    signature = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    return {"svix-id": svix_id, "svix-timestamp": timestamp, "svix-signature": f"v1,{signature}"}


def _event(kind: str, email_id: str) -> dict:
    return {"type": kind, "data": {"email_id": email_id}}


async def _outbox(db: AsyncSession, message_id: str) -> EmailOutbox:
    email = EmailOutbox(
        to_addresses=["driver@example.com"],
        template="driver_assigned",
        status=EmailStatus.SENT,
        provider_message_id=message_id,
    )
    db.add(email)
    await db.flush()
    return email


async def test_invalid_signature_is_rejected(api: AsyncClient) -> None:
    payload = json.dumps(_event("email.delivered", "re_1")).encode()
    wrong_secret = "whsec_" + base64.b64encode(b"wrong-key-wrong-key-wrong-key!!").decode()
    headers = _headers(payload, secret=wrong_secret)
    response = await api.post(WEBHOOK, content=payload, headers=headers)
    assert response.status_code == 400


async def test_delivered_event_marks_the_email_delivered(
    api: AsyncClient, db: AsyncSession
) -> None:
    email = await _outbox(db, "re_delivered_1")
    payload = json.dumps(_event("email.delivered", "re_delivered_1")).encode()
    response = await api.post(WEBHOOK, content=payload, headers=_headers(payload))
    assert response.status_code == 200, response.text
    await db.refresh(email)
    assert email.status is EmailStatus.DELIVERED


async def test_bounced_event_marks_the_email_bounced(api: AsyncClient, db: AsyncSession) -> None:
    email = await _outbox(db, "re_bounced_1")
    payload = json.dumps(_event("email.bounced", "re_bounced_1")).encode()
    response = await api.post(WEBHOOK, content=payload, headers=_headers(payload))
    assert response.status_code == 200, response.text
    await db.refresh(email)
    assert email.status is EmailStatus.BOUNCED


async def test_unknown_message_id_is_ignored(api: AsyncClient) -> None:
    payload = json.dumps(_event("email.delivered", "re_does_not_exist")).encode()
    response = await api.post(WEBHOOK, content=payload, headers=_headers(payload))
    assert response.status_code == 200, response.text


async def test_unhandled_event_type_is_ignored(api: AsyncClient, db: AsyncSession) -> None:
    email = await _outbox(db, "re_opened_1")
    payload = json.dumps(_event("email.opened", "re_opened_1")).encode()
    response = await api.post(WEBHOOK, content=payload, headers=_headers(payload))
    assert response.status_code == 200, response.text
    await db.refresh(email)
    assert email.status is EmailStatus.SENT
