import pytest
from httpx import AsyncClient

from app.main import create_app
from tests.conftest import running


async def test_health_is_ok(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_ready_checks_postgres(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health/ready")
    assert response.status_code == 200, response.text


async def test_ready_reports_unreachable_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://nobody:nobody@127.0.0.1:1/none")
    async with running(create_app()) as http:
        response = await http.get("/api/v1/health/ready")
    assert response.status_code == 503
