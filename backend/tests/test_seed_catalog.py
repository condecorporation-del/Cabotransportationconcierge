import json
from itertools import product

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Extra, Hotel, Promotion, Rate, VehicleClass, Zone
from scripts.seed_catalog import CATALOG_PATH, rate_matrix, seed

CATALOG = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def test_rate_matrix_has_no_gaps() -> None:
    expected = set(
        product(
            (z["slug"] for z in CATALOG["zones"]),
            (v["code"] for v in CATALOG["vehicle_classes"]),
            ("one_way", "round_trip"),
        )
    )
    actual = [(r["zone"], r["vehicle_class"], r["trip_type"]) for r in CATALOG["rates"]]
    assert sorted(actual) == sorted(expected)
    assert all(r["price_cents"] > 0 for r in CATALOG["rates"])
    assert "Cabo San Lucas" in rate_matrix(CATALOG)


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
