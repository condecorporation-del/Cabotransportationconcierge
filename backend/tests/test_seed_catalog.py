import json
from itertools import product

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Extra, Hotel, Promotion, Rate, VehicleClass, Zone
from scripts.seed_catalog import CATALOG_PATH, rate_matrix, seed

CATALOG = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def test_rate_matrix_has_no_gaps() -> None:
    """Aeropuerto y local, ida y redondo, en todas las zonas; la limusina solo en las 5 primeras."""
    zones = [z["slug"] for z in CATALOG["zones"]]
    expected = {
        (zone, vehicle["code"], trip, scope)
        for zone, vehicle, trip, scope in product(
            zones, CATALOG["vehicle_classes"], ("one_way", "round_trip"), ("airport", "local")
        )
        if vehicle["code"] != "LIMOUSINE" or zone in zones[:5]
    }
    actual = [
        (r["zone"], r["vehicle_class"], r["trip_type"], r["service_scope"])
        for r in CATALOG["rates"]
    ]
    assert sorted(actual) == sorted(expected)
    assert all(r["price_cents"] > 0 for r in CATALOG["rates"])
    assert "Cabo San Lucas" in rate_matrix(CATALOG)


async def test_seed_retires_what_left_the_catalog(db: AsyncSession) -> None:
    await seed(db, CATALOG)
    db.add(Zone(slug="old-zone", name={"en": "Old"}, drive_minutes_min=1, drive_minutes_max=2))
    await db.flush()
    await seed(db, CATALOG)
    old = await db.scalar(select(Zone).where(Zone.slug == "old-zone"))
    assert old is not None
    await db.refresh(old)
    assert old.is_active is False


def test_each_hotel_appears_once_in_a_known_zone() -> None:
    zones = {z["slug"] for z in CATALOG["zones"]}
    names = [n.casefold() for h in CATALOG["hotels"] for n in (h["name"], *h["aliases"])]
    assert len({h["slug"] for h in CATALOG["hotels"]}) == len(CATALOG["hotels"])
    assert len(set(names)) == len(names)
    assert {h["zone"] for h in CATALOG["hotels"]} <= zones


async def test_seed_is_idempotent(db: AsyncSession) -> None:
    first = await seed(db, CATALOG)
    second = await seed(db, CATALOG)

    assert first == second
    for model, key in (
        (Zone, "zones"),
        (VehicleClass, "vehicle_classes"),
        (Rate, "rates"),
        (Hotel, "hotels"),
        (Extra, "extras"),
        (Promotion, "promotions"),
    ):
        assert await db.scalar(select(func.count()).select_from(model)) == len(CATALOG[key]), key
