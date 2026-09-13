import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password
from app.models import AdminRole, AdminUser, Company, VehicleClass, Zone
from scripts.ensure_owner import ensure_owner

Catalog = tuple[Company, Zone, VehicleClass]


async def test_owner_is_created_once_with_argon2_hash(db: AsyncSession, catalog: Catalog) -> None:
    slug = catalog[0].slug

    assert await ensure_owner(db, slug, " Owner@Example.com ", "correct horse battery") is True
    assert await ensure_owner(db, slug, "owner@example.com", "a different long password") is False

    owner = (await db.scalars(select(AdminUser))).one()
    assert owner.role is AdminRole.OWNER
    assert owner.email == "owner@example.com"
    assert owner.password_hash.startswith("$argon2id$")
    assert verify_password("correct horse battery", owner.password_hash)


async def test_short_password_is_rejected(db: AsyncSession, catalog: Catalog) -> None:
    with pytest.raises(ValueError, match="12 caracteres"):
        await ensure_owner(db, catalog[0].slug, "owner@example.com", "short")


async def test_unknown_company_fails_with_clear_message(db: AsyncSession) -> None:
    with pytest.raises(LookupError, match="seed_catalog"):
        await ensure_owner(db, "no-existe", "owner@example.com", "correct horse battery")
