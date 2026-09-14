from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminRole, AuditLog, VehicleClass, Zone
from tests.test_admin_booking_actions import _login

ZONES = "/api/v1/admin/zones"
HOTELS = "/api/v1/admin/hotels"
RATES = "/api/v1/admin/rates"
EXTRAS = "/api/v1/admin/extras"
ACTIVITIES = "/api/v1/admin/activities"
PACKAGES = "/api/v1/admin/packages"
PROMOTIONS = "/api/v1/admin/promotions"
SETTINGS = "/api/v1/admin/settings"


async def test_create_and_patch_a_zone(api: AsyncClient, db: AsyncSession) -> None:
    headers = await _login(api, db, role=AdminRole.FINANCE)
    created = await api.post(
        ZONES,
        json={
            "slug": "new-zone",
            "name": {"en": "New Zone", "es": "Zona Nueva"},
            "drive_minutes_min": 20,
            "drive_minutes_max": 30,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text

    patched = await api.patch(
        f"{ZONES}/{created.json()['id']}", json={"is_active": False}, headers=headers
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["is_active"] is False
    assert patched.json()["slug"] == "new-zone"


async def test_create_and_patch_a_hotel(api: AsyncClient, db: AsyncSession) -> None:
    headers = await _login(api, db, role=AdminRole.FINANCE)
    zone_id = await db.scalar(select(Zone.id).where(Zone.slug == "cabo-san-lucas-marina"))
    assert zone_id is not None

    created = await api.post(
        HOTELS,
        json={"zone_id": str(zone_id), "slug": "new-hotel", "name": "New Hotel"},
        headers=headers,
    )
    assert created.status_code == 201, created.text

    patched = await api.patch(
        f"{HOTELS}/{created.json()['id']}", json={"is_active": False}, headers=headers
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["is_active"] is False


async def test_create_and_patch_a_rate_is_audited(api: AsyncClient, db: AsyncSession) -> None:
    """Cierra el criterio de F6.10 ("editar una tarifa deja un log con el diff")."""
    headers = await _login(api, db, role=AdminRole.FINANCE)
    zone = await api.post(
        ZONES,
        json={
            "slug": "rate-test-zone",
            "name": {"en": "Rate Test Zone", "es": "Zona de Prueba"},
            "drive_minutes_min": 20,
            "drive_minutes_max": 30,
        },
        headers=headers,
    )
    zone_id = zone.json()["id"]
    vehicle_class_id = await db.scalar(select(VehicleClass.id).where(VehicleClass.code == "VAN"))

    created = await api.post(
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
    assert created.status_code == 201, created.text
    rate_id = created.json()["id"]

    patched = await api.patch(f"{RATES}/{rate_id}", json={"price_cents": 6000}, headers=headers)
    assert patched.status_code == 200, patched.text
    assert patched.json()["price_cents"] == 6000

    log = await db.scalar(
        select(AuditLog).where(AuditLog.entity == "rates", AuditLog.entity_id == rate_id)
    )
    assert log is not None
    assert log.before == {"price_cents": 5000}
    assert log.after == {"price_cents": 6000}


async def test_create_and_patch_an_extra(api: AsyncClient, db: AsyncSession) -> None:
    headers = await _login(api, db, role=AdminRole.FINANCE)
    created = await api.post(
        EXTRAS,
        json={
            "code": "NEW_EXTRA",
            "name": {"en": "New extra", "es": "Extra nuevo"},
            "price_cents": 1500,
            "pricing_mode": "per_booking",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text

    patched = await api.patch(
        f"{EXTRAS}/{created.json()['id']}", json={"price_cents": 2000}, headers=headers
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["price_cents"] == 2000


async def test_create_and_patch_an_activity(api: AsyncClient, db: AsyncSession) -> None:
    headers = await _login(api, db, role=AdminRole.FINANCE)
    created = await api.post(
        ACTIVITIES,
        json={
            "slug": "new-activity",
            "name": {"en": "New activity", "es": "Actividad nueva"},
            "duration_minutes": 90,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text

    patched = await api.patch(
        f"{ACTIVITIES}/{created.json()['id']}", json={"duration_minutes": 120}, headers=headers
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["duration_minutes"] == 120


async def test_create_and_patch_a_package(api: AsyncClient, db: AsyncSession) -> None:
    headers = await _login(api, db, role=AdminRole.FINANCE)
    created = await api.post(
        PACKAGES,
        json={
            "slug": "new-package",
            "name": {"en": "New package", "es": "Paquete nuevo"},
            "activity_count": 2,
            "price_per_person_cents": 10000,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text

    patched = await api.patch(
        f"{PACKAGES}/{created.json()['id']}",
        json={"price_per_person_cents": 12000},
        headers=headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["price_per_person_cents"] == 12000


async def test_create_and_patch_a_promotion(api: AsyncClient, db: AsyncSession) -> None:
    headers = await _login(api, db, role=AdminRole.FINANCE)
    created = await api.post(
        PROMOTIONS,
        json={
            "code": "TESTPROMO",
            "name": {"en": "Test promo", "es": "Promo de prueba"},
            "discount_type": "percent",
            "value": 10,
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text

    patched = await api.patch(
        f"{PROMOTIONS}/{created.json()['id']}", json={"is_active": False}, headers=headers
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["is_active"] is False


async def test_get_and_patch_settings(api: AsyncClient, db: AsyncSession) -> None:
    headers = await _login(api, db, role=AdminRole.FINANCE)
    current = await api.get(SETTINGS, headers=headers)
    assert current.status_code == 200, current.text

    patched = await api.patch(SETTINGS, json={"cancellation_hours": 48}, headers=headers)
    assert patched.status_code == 200, patched.text
    assert patched.json()["cancellation_hours"] == 48


async def test_create_zone_requires_csrf_header(api: AsyncClient, db: AsyncSession) -> None:
    # Rol con permiso (F6.13): si el 403 llegara solo por CSRF sin este cuidado, no probaría nada.
    await _login(api, db, role=AdminRole.FINANCE)
    response = await api.post(
        ZONES,
        json={
            "slug": "new-zone",
            "name": {"en": "New Zone", "es": "Zona Nueva"},
            "drive_minutes_min": 20,
            "drive_minutes_max": 30,
        },
    )
    assert response.status_code == 403


async def test_viewer_role_cannot_create_a_zone(api: AsyncClient, db: AsyncSession) -> None:
    headers = await _login(api, db, role=AdminRole.VIEWER)
    response = await api.post(
        ZONES,
        json={
            "slug": "new-zone",
            "name": {"en": "New Zone", "es": "Zona Nueva"},
            "drive_minutes_min": 20,
            "drive_minutes_max": 30,
        },
        headers=headers,
    )
    assert response.status_code == 403
