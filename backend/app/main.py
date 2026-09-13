from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.v1 import bookings, catalog, contact, health, quotes, webhooks
from app.api.v1.admin import auth as admin_auth
from app.core.config import get_settings
from app.core.errors import AppError
from app.db import engine_from_url


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.engine = engine_from_url(get_settings().database_url)
    app.state.sessionmaker = async_sessionmaker(app.state.engine, expire_on_commit=False)
    yield
    await app.state.engine.dispose()


async def app_error(_request: Request, exc: Exception) -> JSONResponse:
    error = exc if isinstance(exc, AppError) else AppError("error", "Unexpected error.")
    return JSONResponse(
        {"detail": {"code": error.code, "message": str(error)}}, status_code=error.status_code
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
    app.add_exception_handler(AppError, app_error)
    for module in (health, catalog, quotes, bookings, contact, webhooks, admin_auth):
        app.include_router(module.router, prefix="/api/v1")
    return app


app = create_app()
