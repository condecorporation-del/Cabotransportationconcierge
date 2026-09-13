"""Crea el usuario owner de la empresa una sola vez (WORKPLAN F1.10).

OWNER_EMAIL=... OWNER_PASSWORD=... uv run python -m scripts.ensure_owner

La contraseña se lee del entorno: el script no la inventa ni la imprime.
Si ya existe un admin con ese email, no cambia nada.
"""

import argparse
import asyncio
import os

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.security import hash_password
from app.db import engine_from_url
from app.models import AdminRole, AdminUser, Company

DEFAULT_COMPANY_SLUG = "cabo-transportation-concierge"


async def ensure_owner(session: AsyncSession, company_slug: str, email: str, password: str) -> bool:
    """Devuelve True si creó el owner y False si el email ya existía."""
    company_id = await session.scalar(select(Company.id).where(Company.slug == company_slug))
    if company_id is None:
        raise LookupError(
            f"No existe la empresa '{company_slug}': corre scripts.seed_catalog primero"
        )
    session.info["company_id"] = company_id

    email = email.strip().lower()
    if await session.scalar(select(AdminUser.id).where(func.lower(AdminUser.email) == email)):
        return False
    session.add(AdminUser(email=email, password_hash=hash_password(password), role=AdminRole.OWNER))
    await session.flush()
    return True


async def _main(company_slug: str) -> None:
    email = os.environ.get("OWNER_EMAIL", "")
    password = os.environ.get("OWNER_PASSWORD", "")
    if "@" not in email or not password:
        raise SystemExit("Define OWNER_EMAIL y OWNER_PASSWORD en el entorno.")
    engine = engine_from_url(get_settings().database_url, pooled=False)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        created = await ensure_owner(session, company_slug, email, password)
        await session.commit()
    await engine.dispose()
    print(f"Owner {email.strip().lower()}: {'creado' if created else 'ya existía, sin cambios'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--company-slug", default=DEFAULT_COMPANY_SLUG)
    asyncio.run(_main(parser.parse_args().company_slug))
