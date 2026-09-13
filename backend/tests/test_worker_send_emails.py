from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Company, EmailOutbox, EmailStatus
from app.services.resend_gateway import API_URL, ResendGateway
from app.worker.send_emails import MAX_ATTEMPTS, run_once

TO = ["ana@example.com"]


@pytest.fixture(autouse=True)
async def _company(db: AsyncSession) -> None:
    company = Company(name="CTC", slug="ctc-worker-test")
    db.add(company)
    await db.flush()
    db.info["company_id"] = company.id


async def _outbox(db: AsyncSession, **overrides: object) -> EmailOutbox:
    fields: dict[str, object] = {
        "to_addresses": TO,
        "template": "contact_ack",
        "language": "en",
        "context": {"name": "Ana"},
    } | overrides
    email = EmailOutbox(**fields)
    db.add(email)
    await db.flush()
    return email


@respx.mock(base_url=API_URL)
async def test_successful_send_marks_sent_with_the_provider_id(
    db: AsyncSession, respx_mock: respx.MockRouter
) -> None:
    respx_mock.post("/emails").respond(200, json={"id": "email_1"})
    email = await _outbox(db)

    processed = await run_once(db, ResendGateway("re_test"))

    assert processed == 1
    await db.refresh(email)
    assert (email.status, email.provider_message_id, email.attempts) == (
        EmailStatus.SENT,
        "email_1",
        0,
    )
    assert email.sent_at is not None


@respx.mock(base_url=API_URL)
async def test_failure_schedules_a_retry_with_backoff(
    db: AsyncSession, respx_mock: respx.MockRouter
) -> None:
    respx_mock.post("/emails").respond(422, json={"message": "Invalid recipient"})
    email = await _outbox(db)

    await run_once(db, ResendGateway("re_test"))

    await db.refresh(email)
    assert (email.status, email.attempts, email.last_error) == (
        EmailStatus.PENDING,
        1,
        "Invalid recipient",
    )
    assert email.next_attempt_at > datetime.now(UTC)


@respx.mock(base_url=API_URL)
async def test_gives_up_after_the_maximum_number_of_attempts(
    db: AsyncSession, respx_mock: respx.MockRouter
) -> None:
    respx_mock.post("/emails").respond(422, json={"message": "Invalid recipient"})
    email = await _outbox(db, attempts=MAX_ATTEMPTS - 1)

    await run_once(db, ResendGateway("re_test"))

    await db.refresh(email)
    assert (email.status, email.attempts) == (EmailStatus.FAILED, MAX_ATTEMPTS)


async def test_a_pending_email_not_due_yet_is_left_alone(db: AsyncSession) -> None:
    await _outbox(db, next_attempt_at=datetime.now(UTC) + timedelta(hours=1))

    processed = await run_once(db, ResendGateway("re_test"))

    assert processed == 0


@respx.mock(base_url=API_URL)
async def test_network_error_is_treated_as_a_failure_to_retry(
    db: AsyncSession, respx_mock: respx.MockRouter
) -> None:
    respx_mock.post("/emails").mock(side_effect=httpx.ConnectError("down"))
    email = await _outbox(db)

    await run_once(db, ResendGateway("re_test"))

    await db.refresh(email)
    assert (email.status, email.attempts) == (EmailStatus.PENDING, 1)


@pytest.mark.parametrize("template", ["contact_ack", "booking_confirmed"])
async def test_already_sent_or_failed_emails_are_never_picked_up(
    db: AsyncSession, template: str
) -> None:
    for status in (EmailStatus.SENT, EmailStatus.FAILED, EmailStatus.SENDING):
        await _outbox(db, status=status, template=template)

    processed = await run_once(db, ResendGateway("re_test"))

    assert processed == 0
    statuses = {row.status for row in (await db.scalars(select(EmailOutbox))).all()}
    assert statuses == {EmailStatus.SENT, EmailStatus.FAILED, EmailStatus.SENDING}
