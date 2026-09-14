import pyotp
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import read_admin_totp_challenge_token
from app.models import AdminRole, VehicleClass, Zone
from tests.test_admin_auth import PASSWORD, _admin, _csrf_headers
from tests.test_admin_auth import URL as AUTH_URL
from tests.test_admin_booking_actions import _login as _login_dispatcher

USERS = "/api/v1/admin/users"
AUDIT_LOGS = "/api/v1/admin/audit-logs"
RATES = "/api/v1/admin/rates"
ZONES = "/api/v1/admin/zones"


async def _login_owner(
    api: AsyncClient, db: AsyncSession, email: str = "owner@example.com"
) -> dict[str, str]:
    await _admin(db, role=AdminRole.OWNER, email=email)
    login = (
        await api.post(AUTH_URL + "/login", json={"email": email, "password": PASSWORD})
    ).json()
    assert login["outcome"] == "totp_setup_required"
    decoded = read_admin_totp_challenge_token(login["challenge_token"])
    assert decoded is not None
    _, secret = decoded
    assert secret is not None
    verify = await api.post(
        AUTH_URL + "/totp/verify",
        json={"challenge_token": login["challenge_token"], "code": pyotp.TOTP(secret).now()},
    )
    assert verify.status_code == 200, verify.text
    return _csrf_headers(api)


async def test_owner_can_create_and_list_a_user(api: AsyncClient, db: AsyncSession) -> None:
    headers = await _login_owner(api, db)
    created = await api.post(
        USERS,
        json={
            "email": "new-dispatcher@example.com",
            "password": "Sup3rSecret!23",
            "role": "dispatcher",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["role"] == "dispatcher"

    listing = await api.get(USERS, headers=headers)
    assert "new-dispatcher@example.com" in [row["email"] for row in listing.json()]


async def test_creating_a_user_with_a_duplicate_email_is_rejected(
    api: AsyncClient, db: AsyncSession
) -> None:
    headers = await _login_owner(api, db)
    body = {"email": "dup@example.com", "password": "Sup3rSecret!23", "role": "viewer"}
    first = await api.post(USERS, json=body, headers=headers)
    assert first.status_code == 201, first.text

    second = await api.post(USERS, json=body, headers=headers)
    assert second.status_code == 422
    assert second.json()["detail"]["code"] == "email_taken"


async def test_patching_a_users_role_leaves_an_audit_log(
    api: AsyncClient, db: AsyncSession
) -> None:
    headers = await _login_owner(api, db)
    created = (
        await api.post(
            USERS,
            json={
                "email": "promote-me@example.com",
                "password": "Sup3rSecret!23",
                "role": "viewer",
            },
            headers=headers,
        )
    ).json()

    patched = await api.patch(f"{USERS}/{created['id']}", json={"role": "finance"}, headers=headers)
    assert patched.status_code == 200, patched.text
    assert patched.json()["role"] == "finance"

    logs = await api.get(
        AUDIT_LOGS, params={"entity": "admin_users", "entity_id": created["id"]}, headers=headers
    )
    assert logs.status_code == 200, logs.text
    [entry] = logs.json()["items"]
    assert entry["before"] == {"role": "viewer"}
    assert entry["after"] == {"role": "finance"}


async def test_non_owner_cannot_create_a_user(api: AsyncClient, db: AsyncSession) -> None:
    headers = await _login_dispatcher(api, db)
    response = await api.post(
        USERS,
        json={"email": "someone@example.com", "password": "Sup3rSecret!23", "role": "viewer"},
        headers=headers,
    )
    assert response.status_code == 403


async def test_dispatcher_cannot_edit_a_rate(api: AsyncClient, db: AsyncSession) -> None:
    """Criterio de F6.13: un dispatcher no puede editar tarifas (403)."""
    headers = await _login_dispatcher(api, db)
    zone_id = await db.scalar(select(Zone.id).where(Zone.slug == "cabo-san-lucas-marina"))
    vehicle_class_id = await db.scalar(select(VehicleClass.id).where(VehicleClass.code == "VAN"))

    response = await api.post(
        RATES,
        json={
            "zone_id": str(zone_id),
            "vehicle_class_id": str(vehicle_class_id),
            "trip_type": "one_way",
            "service_scope": "local",
            "price_cents": 5000,
        },
        headers=headers,
    )
    assert response.status_code == 403


async def test_dispatcher_cannot_create_a_zone_either(api: AsyncClient, db: AsyncSession) -> None:
    """El permiso más estricto de F6.13 cubre todo el catálogo, no solo /rates."""
    dispatcher_headers = await _login_dispatcher(api, db)
    blocked = await api.post(
        ZONES,
        json={
            "slug": "blocked-zone",
            "name": {"en": "Blocked", "es": "Bloqueada"},
            "drive_minutes_min": 10,
            "drive_minutes_max": 20,
        },
        headers=dispatcher_headers,
    )
    assert blocked.status_code == 403


async def test_audit_logs_are_paginated_and_filterable(api: AsyncClient, db: AsyncSession) -> None:
    headers = await _login_owner(api, db)
    await api.post(
        USERS,
        json={"email": "one@example.com", "password": "Sup3rSecret!23", "role": "viewer"},
        headers=headers,
    )
    other = (
        await api.post(
            USERS,
            json={"email": "two@example.com", "password": "Sup3rSecret!23", "role": "viewer"},
            headers=headers,
        )
    ).json()
    await api.patch(f"{USERS}/{other['id']}", json={"is_active": False}, headers=headers)

    response = await api.get(
        AUDIT_LOGS, params={"entity": "admin_users", "page": 1, "page_size": 1}, headers=headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["items"]) == 1
    assert body["total"] >= 1
