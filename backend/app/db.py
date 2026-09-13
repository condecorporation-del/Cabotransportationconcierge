import enum
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import Request
from sqlalchemy import DateTime, Enum, MetaData, Time, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import NullPool

_TRANSACTION_POOLER_PORT = 6543


def normalize_url(url: str) -> str:
    """Fuerza el driver asyncpg y quita `pgbouncer=true`, que asyncpg rechaza (lección ClassVIP)."""
    scheme, rest = url.split("://", 1)
    if scheme in ("postgres", "postgresql"):
        url = f"postgresql+asyncpg://{rest}"
    parts = urlsplit(url)
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if k != "pgbouncer"])
    return urlunsplit(parts._replace(query=query))


def engine_from_url(url: str, *, pooled: bool = True) -> AsyncEngine:
    """Engine apto para Supabase: SSL fuera de localhost y pooler de transacciones sin caché."""
    url = normalize_url(url)
    parts = urlsplit(url)
    connect_args: dict[str, Any] = (
        {} if parts.hostname in ("localhost", "127.0.0.1") else {"ssl": "require"}
    )
    if parts.port == _TRANSACTION_POOLER_PORT:
        connect_args |= {
            "statement_cache_size": 0,
            "prepared_statement_name_func": lambda: f"__asyncpg_{uuid.uuid4()}__",
        }
        pooled = False
    if not pooled:
        return create_async_engine(url, poolclass=NullPool, connect_args=connect_args)
    return create_async_engine(
        url,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args=connect_args,
    )


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Sesión por request. Los servicios hacen commit explícito; lo no confirmado se descarta."""
    async with request.app.state.sessionmaker() as session:
        yield session


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )
    type_annotation_map = {  # noqa: RUF012  (configuración declarativa de SQLAlchemy)
        datetime: DateTime(timezone=True),
        time: Time(),
        dict[str, Any]: JSONB,
        # Enums como texto con CHECK: los downgrades no dejan tipos huérfanos en Postgres.
        enum.Enum: Enum(
            enum.Enum,
            native_enum=False,
            create_constraint=True,
            length=32,
            values_callable=lambda members: [m.value for m in members],
        ),
    }


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
