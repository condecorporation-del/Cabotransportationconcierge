from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AiConversation,
    AiMessage,
    Company,
    EmailOutbox,
    EmailStatus,
    MessageRole,
    Review,
    ReviewSource,
    VehicleClass,
    Zone,
)

Catalog = tuple[Company, Zone, VehicleClass]


async def test_outbox_email_starts_pending_and_ready_to_send(
    db: AsyncSession, catalog: Catalog
) -> None:
    email = EmailOutbox(to_addresses=["ana@example.com"], template="booking_confirmed")
    db.add(email)
    await db.flush()
    await db.refresh(email)

    assert email.status is EmailStatus.PENDING
    assert email.attempts == 0
    assert email.next_attempt_at is not None


async def test_deleting_conversation_deletes_its_messages(
    db: AsyncSession, catalog: Catalog
) -> None:
    conversation = AiConversation(visitor_token_hash="a" * 64)
    db.add(conversation)
    await db.flush()
    db.add(AiMessage(conversation_id=conversation.id, role=MessageRole.USER, content="Hola"))
    await db.flush()

    await db.delete(conversation)
    await db.flush()

    assert await db.scalar(select(func.count()).select_from(AiMessage)) == 0


async def test_review_rating_between_one_and_five(db: AsyncSession, catalog: Catalog) -> None:
    db.add(
        Review(
            author="Ana",
            source=ReviewSource.GOOGLE,
            rating=6,
            body="Great",
            review_date=date(2026, 9, 1),
        )
    )
    with pytest.raises(IntegrityError, match="ck_reviews_rating_range"):
        await db.flush()
