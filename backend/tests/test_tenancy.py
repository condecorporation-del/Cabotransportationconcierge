import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminRole, AdminUser, Company
from app.tenancy import CrossTenantWriteError


async def _two_companies(db: AsyncSession) -> tuple[Company, Company]:
    first, second = Company(name="A", slug="tenant-a"), Company(name="B", slug="tenant-b")
    db.add_all([first, second])
    await db.flush()
    return first, second


def _admin(email: str, company: Company | None = None) -> AdminUser:
    return AdminUser(
        company_id=company.id if company else None,
        email=email,
        password_hash="x",
        role=AdminRole.VIEWER,
    )


async def test_queries_only_see_the_session_company(db: AsyncSession) -> None:
    first, second = await _two_companies(db)
    db.add_all([_admin("a@example.com", first), _admin("b@example.com", second)])
    await db.flush()

    db.info["company_id"] = second.id

    assert (await db.scalars(select(AdminUser))).one().email == "b@example.com"
    assert await db.scalar(select(func.count()).select_from(AdminUser)) == 1


async def test_flush_fills_company_and_rejects_other_company(db: AsyncSession) -> None:
    first, second = await _two_companies(db)
    db.info["company_id"] = first.id

    own = _admin("own@example.com")
    db.add(own)
    await db.flush()
    assert own.company_id == first.id

    db.add(_admin("intruder@example.com", second))
    with pytest.raises(CrossTenantWriteError):
        await db.flush()
