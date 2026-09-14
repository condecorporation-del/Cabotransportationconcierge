from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminRole
from tests.test_admin_auth import _admin
from tests.test_admin_booking_actions import _login

URL = "/api/v1/admin/tasks"


async def test_create_and_list_a_task(api: AsyncClient, db: AsyncSession) -> None:
    headers = await _login(api, db)
    created = await api.post(URL, json={"title": "Wash the Suburban"}, headers=headers)
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "pending"

    listing = await api.get(URL, headers=headers)
    assert "Wash the Suburban" in [row["title"] for row in listing.json()]


async def test_patch_marks_a_task_done(api: AsyncClient, db: AsyncSession) -> None:
    headers = await _login(api, db)
    created = (await api.post(URL, json={"title": "Wash the Suburban"}, headers=headers)).json()

    response = await api.patch(f"{URL}/{created['id']}", json={"status": "done"}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "done"
    assert response.json()["title"] == "Wash the Suburban"


async def test_status_filter_narrows_the_list(api: AsyncClient, db: AsyncSession) -> None:
    headers = await _login(api, db)
    await api.post(URL, json={"title": "Pending one"}, headers=headers)
    done = (await api.post(URL, json={"title": "Done one"}, headers=headers)).json()
    await api.patch(f"{URL}/{done['id']}", json={"status": "done"}, headers=headers)

    response = await api.get(URL, params={"status": "pending"}, headers=headers)
    titles = [row["title"] for row in response.json()]
    assert "Pending one" in titles
    assert "Done one" not in titles


async def test_assigning_to_an_unknown_admin_is_rejected(
    api: AsyncClient, db: AsyncSession
) -> None:
    headers = await _login(api, db)
    response = await api.post(
        URL,
        json={
            "title": "Wash the Suburban",
            "assigned_to_admin_id": "00000000-0000-0000-0000-000000000000",
        },
        headers=headers,
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "assignee_not_found"


async def test_assigning_to_a_real_admin_works(api: AsyncClient, db: AsyncSession) -> None:
    headers = await _login(api, db)
    other = await _admin(db, email="dispatcher2@example.com")
    response = await api.post(
        URL,
        json={"title": "Wash the Suburban", "assigned_to_admin_id": str(other.id)},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["assigned_to_admin_id"] == str(other.id)


async def test_delete_removes_the_task(api: AsyncClient, db: AsyncSession) -> None:
    headers = await _login(api, db)
    created = (await api.post(URL, json={"title": "Wash the Suburban"}, headers=headers)).json()

    response = await api.delete(f"{URL}/{created['id']}", headers=headers)
    assert response.status_code == 204, response.text

    listing = (await api.get(URL, headers=headers)).json()
    assert created["id"] not in [row["id"] for row in listing]


async def test_create_requires_csrf_header(api: AsyncClient, db: AsyncSession) -> None:
    await _login(api, db)
    response = await api.post(URL, json={"title": "Wash the Suburban"})
    assert response.status_code == 403


async def test_viewer_role_cannot_create_a_task(api: AsyncClient, db: AsyncSession) -> None:
    headers = await _login(api, db, role=AdminRole.VIEWER)
    response = await api.post(URL, json={"title": "Wash the Suburban"}, headers=headers)
    assert response.status_code == 403
