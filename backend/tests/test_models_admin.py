import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminRole, AdminUser, Company


def _admin(company: Company, email: str) -> AdminUser:
    return AdminUser(company_id=company.id, email=email, password_hash="x", role=AdminRole.OWNER)


async def test_admin_email_is_unique_per_company_ignoring_case(db: AsyncSession) -> None:
    first, second = Company(name="A", slug="a"), Company(name="B", slug="b")
    db.add_all([first, second])
    await db.flush()

    db.add_all(
        [
            _admin(first, "Owner@Example.com"),
            _admin(first, "dispatch@example.com"),
            _admin(second, "owner@example.com"),
        ]
    )
    await db.flush()

    db.add(_admin(first, "OWNER@example.com"))
    with pytest.raises(IntegrityError):
        await db.flush()


async def test_company_slug_is_unique(db: AsyncSession) -> None:
    db.add_all([Company(name="A", slug="same"), Company(name="B", slug="same")])
    with pytest.raises(IntegrityError):
        await db.flush()
