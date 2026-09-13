from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.v1 import health
from app.core.config import get_settings
from app.db import engine_from_url


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.engine = engine_from_url(get_settings().database_url)
    app.state.sessionmaker = async_sessionmaker(app.state.engine, expire_on_commit=False)
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
