from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.v1 import catalog, health, quotes
from app.core.config import get_settings
from app.db import engine_from_url
from app.services.pricing import QuoteError


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.engine = engine_from_url(get_settings().database_url)
    app.state.sessionmaker = async_sessionmaker(app.state.engine, expire_on_commit=False)
    yield
    await app.state.engine.dispose()


async def quote_error(_request: Request, exc: Exception) -> JSONResponse:
    code = exc.code if isinstance(exc, QuoteError) else "invalid_quote"
    return JSONResponse(
        {"detail": {"code": code, "message": str(exc)}},
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )


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
    app.state.rate_limits = {}
    app.add_exception_handler(QuoteError, quote_error)
    for module in (health, catalog, quotes):
        app.include_router(module.router, prefix="/api/v1")
    return app


app = create_app()
