from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine

from app.api.v1 import health
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Pool chico: el Session Pooler de Supabase limita conexiones por proyecto (WORKPLAN D2).
    app.state.engine = create_async_engine(
        get_settings().database_url,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=300,
    )
    yield
    await app.state.engine.dispose()


def create_app() -> FastAPI:
    show_docs = get_settings().environment != "production"
    app = FastAPI(
        title="Cabo Transportation Concierge API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if show_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if show_docs else None,
    )
    app.include_router(health.router, prefix="/api/v1")
    return app


app = create_app()
