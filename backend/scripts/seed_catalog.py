"""Carga o actualiza el catálogo de la empresa desde scripts/data/catalog.json (WORKPLAN F1.9).

uv run python -m scripts.seed_catalog --dry-run   # solo imprime la matriz de tarifas
uv run python -m scripts.seed_catalog             # inserta o actualiza (idempotente)
"""

import argparse
import asyncio
import io
import json
import sys
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.db import Base, engine_from_url
from app.models import (
    Activity,
    ActivityPackage,
    Company,
    CompanySettings,
    Extra,
    Hotel,
    Promotion,
    Rate,
    VehicleClass,
    Zone,
)

CATALOG_PATH = Path(__file__).parent / "data" / "catalog.json"
COUNTED = (
    "zones",
    "vehicle_classes",
    "rates",
    "hotels",
    "extras",
    "activities",
    "activity_packages",
    "promotions",
)


async def _upsert(
    session: AsyncSession, model: type[Base], rows: list[dict[str, Any]], keys: list[str]
) -> dict[tuple[Any, ...], uuid.UUID]:
    """Inserta o actualiza por la llave única y devuelve {valores de la llave: id}."""
    if not rows:
        return {}
    table = model.__table__
    values = insert(model).values(rows)
    statement = values.on_conflict_do_update(
        index_elements=keys,
        set_={col: values.excluded[col] for col in rows[0] if col not in keys},
    ).returning(table.c.id, *(table.c[key] for key in keys))
    result = await session.execute(statement)
    return {tuple(row[1:]): row[0] for row in result}


async def seed(session: AsyncSession, catalog: dict[str, Any]) -> dict[str, int]:
    company = catalog["company"]
    ids = await _upsert(session, Company, [company], ["slug"])
    company_id = ids[(company["slug"],)]
    session.info["company_id"] = company_id
    await session.execute(
        insert(CompanySettings).values(company_id=company_id).on_conflict_do_nothing()
    )

    def owned(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{**row, "company_id": company_id, "is_active": True} for row in rows]

    zone_ids = await _upsert(session, Zone, owned(catalog["zones"]), ["company_id", "slug"])
    vehicle_ids = await _upsert(
        session, VehicleClass, owned(catalog["vehicle_classes"]), ["company_id", "code"]
    )
    zone = {slug: zid for (_, slug), zid in zone_ids.items()}
    vehicle = {code: vid for (_, code), vid in vehicle_ids.items()}

    hotels = [
        {"slug": h["slug"], "name": h["name"], "zone_id": zone[h["zone"]], "aliases": h["aliases"]}
        for h in catalog["hotels"]
    ]
    rates = [
        {
            "zone_id": zone[r["zone"]],
            "vehicle_class_id": vehicle[r["vehicle_class"]],
            "trip_type": r["trip_type"],
            "service_scope": r["service_scope"],
            "price_cents": r["price_cents"],
        }
        for r in catalog["rates"]
    ]
    await _upsert(session, Hotel, owned(hotels), ["company_id", "slug"])
    await _upsert(
        session,
        Rate,
        owned(rates),
        ["company_id", "zone_id", "vehicle_class_id", "trip_type", "service_scope"],
    )
    await _upsert(session, Extra, owned(catalog["extras"]), ["company_id", "code"])
    # Lo que salió del catálogo se desactiva (no se borra: puede tener reservas).
    retired: list[tuple[Any, Any, list[str]]] = [
        (Zone, Zone.slug, [z["slug"] for z in catalog["zones"]]),
        (VehicleClass, VehicleClass.code, [v["code"] for v in catalog["vehicle_classes"]]),
        (Extra, Extra.code, [e["code"] for e in catalog["extras"]]),
    ]
    for model, column, present in retired:
        await session.execute(
            update(model)
            .where(model.company_id == company_id, column.not_in(present))
            .values(is_active=False)
        )
    await _upsert(session, Activity, owned(catalog["activities"]), ["company_id", "slug"])
    await _upsert(
        session, ActivityPackage, owned(catalog["activity_packages"]), ["company_id", "slug"]
    )

    # Promociones sin código no tienen llave única: se reconocen por su nombre en inglés.
    for promo in catalog["promotions"]:
        fields = {
            **promo,
            "travel_from": date.fromisoformat(promo["travel_from"]),
            "travel_to": date.fromisoformat(promo["travel_to"]),
        }
        existing = await session.scalar(
            select(Promotion).where(Promotion.name["en"].astext == promo["name"]["en"])
        )
        if existing is None:
            session.add(Promotion(**fields))
        else:
            for field, value in fields.items():
                setattr(existing, field, value)
    await session.flush()

    return {key: len(catalog[key]) for key in COUNTED}


def rate_matrix(catalog: dict[str, Any]) -> str:
    """Tarifas de aeropuerto (ida / redondo) por zona y vehículo; "—" donde no hay servicio."""
    cents = {
        (r["zone"], r["vehicle_class"], r["trip_type"]): r["price_cents"]
        for r in catalog["rates"]
        if r["service_scope"] == "airport"
    }
    codes = [v["code"] for v in catalog["vehicle_classes"]]

    def pair(zone: str, code: str) -> str:
        if (zone, code, "one_way") not in cents:
            return "—"
        one_way, round_trip = (
            cents[(zone, code, trip)] // 100 for trip in ("one_way", "round_trip")
        )
        return f"${one_way:,} / ${round_trip:,}"

    header = f"{'Zona':<40}" + "".join(f"{code:>18}" for code in codes)
    rows = [
        f"{z['name']['es']:<40}" + "".join(f"{pair(z['slug'], c):>18}" for c in codes)
        for z in catalog["zones"]
    ]
    return "\n".join([header, "-" * len(header), *rows])


async def _main(dry_run: bool) -> None:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")  # acentos correctos en la consola de Windows
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    print(f"Estado del catálogo: {catalog['meta']['status']}\n{rate_matrix(catalog)}\n")
    if dry_run:
        return
    engine = engine_from_url(get_settings().database_url, pooled=False)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        counts = await seed(session, catalog)
        await session.commit()
    await engine.dispose()
    print("Cargado:", counts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="solo imprime la matriz de tarifas")
    asyncio.run(_main(parser.parse_args().dry_run))
