from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminRole, Vehicle, VehicleClass
from tests.test_admin_booking_actions import _login

DRIVERS = "/api/v1/admin/drivers"
VEHICLES = "/api/v1/admin/vehicles"
VEHICLE_CLASSES = "/api/v1/admin/vehicle-classes"


async def test_create_and_list_a_driver(api: AsyncClient, db: AsyncSession) -> None:
    headers = await _login(api, db)
    created = await api.post(
        DRIVERS, json={"name": "Carlos", "phone": "+52 624 555 0001"}, headers=headers
    )
    assert created.status_code == 201, created.text
    listing = await api.get(DRIVERS, headers=headers)
    assert "Carlos" in [row["name"] for row in listing.json()]


async def test_patch_a_driver_deactivates_without_touching_other_fields(
    api: AsyncClient, db: AsyncSession
) -> None:
    headers = await _login(api, db)
    created = (
        await api.post(
            DRIVERS, json={"name": "Carlos", "phone": "+52 624 555 0001"}, headers=headers
        )
    ).json()

    response = await api.patch(
        f"{DRIVERS}/{created['id']}", json={"is_active": False}, headers=headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_active"] is False
    assert body["name"] == "Carlos"


async def test_create_driver_requires_csrf_header(api: AsyncClient, db: AsyncSession) -> None:
    await _login(api, db)
    response = await api.post(DRIVERS, json={"name": "Carlos", "phone": "+52 624 555 0001"})
    assert response.status_code == 403


async def test_viewer_role_cannot_create_a_driver(api: AsyncClient, db: AsyncSession) -> None:
    headers = await _login(api, db, role=AdminRole.VIEWER)
    response = await api.post(
        DRIVERS, json={"name": "Carlos", "phone": "+52 624 555 0001"}, headers=headers
    )
    assert response.status_code == 403


async def test_viewer_role_can_still_list_drivers(api: AsyncClient, db: AsyncSession) -> None:
    headers = await _login(api, db, role=AdminRole.VIEWER)
    response = await api.get(DRIVERS, headers=headers)
    assert response.status_code == 200


async def test_create_and_patch_a_vehicle(api: AsyncClient, db: AsyncSession) -> None:
    headers = await _login(api, db)
    vehicle_class_id = await db.scalar(
        select(VehicleClass.id).where(VehicleClass.code == "SUBURBAN")
    )

    created = await api.post(
        VEHICLES,
        json={
            "vehicle_class_id": str(vehicle_class_id),
            "plate": "ABC-123",
            "make": "Chevrolet",
            "model": "Suburban",
            "capacity": 6,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text

    patched = await api.patch(
        f"{VEHICLES}/{created.json()['id']}", json={"is_active": False}, headers=headers
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["is_active"] is False

    [vehicle] = (await db.scalars(select(Vehicle).where(Vehicle.plate == "ABC-123"))).all()
    assert vehicle.is_active is False


async def test_create_and_patch_a_vehicle_class(api: AsyncClient, db: AsyncSession) -> None:
    headers = await _login(api, db)
    created = await api.post(
        VEHICLE_CLASSES,
        json={"code": "MINIVAN", "name": "Minivan", "max_pax": 7, "max_bags": 5},
        headers=headers,
    )
    assert created.status_code == 201, created.text

    patched = await api.patch(
        f"{VEHICLE_CLASSES}/{created.json()['id']}", json={"sort": 9}, headers=headers
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["sort"] == 9
    assert patched.json()["code"] == "MINIVAN"
