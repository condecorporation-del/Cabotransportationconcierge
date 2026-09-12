import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health() -> dict[str, str]:
    """Liveness: responde sin tocar la base de datos."""
    return {"status": "ok", "time": datetime.now(UTC).isoformat()}


@router.get("/ready")
async def ready(request: Request, response: Response) -> dict[str, str]:
    """Readiness: confirma que Postgres responde en menos de 2 s."""
    try:
        async with asyncio.timeout(2), request.app.state.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except (OSError, SQLAlchemyError):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable"}
    return {"status": "ready"}
