from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditActor, AuditLog
from tests.test_admin_booking_actions import _login
from tests.test_admin_tasks import URL as TASKS_URL

DRIVERS = "/api/v1/admin/drivers"


async def test_editing_a_driver_leaves_an_audit_log_with_the_diff(
    api: AsyncClient, db: AsyncSession
) -> None:
    """Criterio de F6.10: editar deja un log con el diff, sin que el endpoint lo arme a mano."""
    headers = await _login(api, db)
    created = (
        await api.post(
            DRIVERS, json={"name": "Carlos", "phone": "+52 624 555 0001"}, headers=headers
        )
    ).json()

    response = await api.patch(
        f"{DRIVERS}/{created['id']}", json={"phone": "+52 624 555 9999"}, headers=headers
    )
    assert response.status_code == 200, response.text

    log = await db.scalar(
        select(AuditLog).where(
            AuditLog.entity == "drivers",
            AuditLog.entity_id == created["id"],
            AuditLog.action == "update",
        )
    )
    assert log is not None
    assert log.actor is AuditActor.ADMIN
    assert log.admin_user_id is not None
    assert log.before == {"phone": "+52 624 555 0001"}
    assert log.after == {"phone": "+52 624 555 9999"}


async def test_patch_that_changes_nothing_leaves_no_audit_log(
    api: AsyncClient, db: AsyncSession
) -> None:
    headers = await _login(api, db)
    created = (
        await api.post(
            DRIVERS, json={"name": "Carlos", "phone": "+52 624 555 0001"}, headers=headers
        )
    ).json()

    response = await api.patch(
        f"{DRIVERS}/{created['id']}", json={"phone": "+52 624 555 0001"}, headers=headers
    )
    assert response.status_code == 200, response.text

    log = await db.scalar(
        select(AuditLog).where(
            AuditLog.entity == "drivers",
            AuditLog.entity_id == created["id"],
            AuditLog.action == "update",
        )
    )
    assert log is None


async def test_editing_a_task_is_also_audited_automatically(
    api: AsyncClient, db: AsyncSession
) -> None:
    """El mismo mecanismo cubre cualquier modelo en AUDITED_MODELS, no solo choferes."""
    headers = await _login(api, db)
    created = (
        await api.post(TASKS_URL, json={"title": "Wash the Suburban"}, headers=headers)
    ).json()

    await api.patch(f"{TASKS_URL}/{created['id']}", json={"status": "done"}, headers=headers)

    log = await db.scalar(
        select(AuditLog).where(
            AuditLog.entity == "admin_tasks", AuditLog.entity_id == created["id"]
        )
    )
    assert log is not None
    assert log.before == {"status": "pending"}
    assert log.after == {"status": "done"}
