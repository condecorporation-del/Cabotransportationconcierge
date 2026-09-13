import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.admin.deps import require_role
from app.models import AdminRole
from tests.test_admin_auth import PASSWORD, URL, _admin, _csrf_headers


async def _login(api: AsyncClient, db: AsyncSession) -> None:
    await _admin(db, role=AdminRole.DISPATCHER)
    response = await api.post(
        URL + "/login", json={"email": "admin@example.com", "password": PASSWORD}
    )
    assert response.status_code == 200, response.text


async def test_mutation_without_csrf_header_is_rejected(api: AsyncClient, db: AsyncSession) -> None:
    """Criterio de F6.3: un POST autenticado sin el header responde 403, no 401."""
    await _login(api, db)
    response = await api.post(URL + "/logout")
    assert response.status_code == 403


async def test_mutation_with_mismatched_csrf_header_is_rejected(
    api: AsyncClient, db: AsyncSession
) -> None:
    await _login(api, db)
    response = await api.post(URL + "/logout", headers={"X-CSRF-Token": "not-the-real-token"})
    assert response.status_code == 403


async def test_mutation_with_matching_csrf_header_succeeds(
    api: AsyncClient, db: AsyncSession
) -> None:
    await _login(api, db)
    response = await api.post(URL + "/logout", headers=_csrf_headers(api))
    assert response.status_code == 204


async def test_safe_methods_do_not_need_the_csrf_header(api: AsyncClient, db: AsyncSession) -> None:
    await _login(api, db)
    response = await api.get(URL + "/me")
    assert response.status_code == 200


async def test_require_role_allows_matching_role_and_blocks_others() -> None:
    check = require_role(AdminRole.OWNER, AdminRole.MANAGER)

    owner = AdminUserStub(AdminRole.OWNER)
    assert await check(owner) is owner

    dispatcher = AdminUserStub(AdminRole.DISPATCHER)
    with pytest.raises(HTTPException) as exc_info:
        await check(dispatcher)
    assert exc_info.value.status_code == 403


class AdminUserStub:
    """Solo lo que `require_role` mira; no hace falta guardarlo en la base para probarlo."""

    def __init__(self, role: AdminRole) -> None:
        self.role = role
