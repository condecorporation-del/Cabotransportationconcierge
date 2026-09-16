import unicodedata

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import (
    CompanySettings,
    Hotel,
    Rate,
    ServiceScope,
    TripType,
    VehicleClass,
    Zone,
)
from app.schemas.catalog import CompanyOut, HotelMatch, HotelPage, RateOut, ZoneOut

MIN_QUERY_LENGTH = 2
MIN_SIMILARITY = 0.3


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.strip().lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))[:60]


async def company_public(session: AsyncSession) -> CompanyOut:
    """Los datos de la empresa que el sitio público muestra (F7.5).

    `CompanyOut` decide qué sale; aquí no se arma el diccionario a mano para que agregar una
    columna sensible a `company_settings` no la publique sin querer.
    """
    settings = await session.scalar(select(CompanySettings))
    if settings is None:
        raise AppError("company_not_configured", "Company settings are missing.")
    return CompanyOut.model_validate(settings)


async def search_hotels(session: AsyncSession, query: str, limit: int = 10) -> list[HotelMatch]:
    """Hoteles por nombre o alias, sin importar acentos ni mayúsculas (F2.5).

    Primero los que empiezan con lo escrito y luego por similitud de trigramas (pg_trgm).
    """
    term = _normalize(query)
    if len(term) < MIN_QUERY_LENGTH:
        return []
    haystack = func.lower(
        func.translate(
            Hotel.name + " " + func.array_to_string(Hotel.aliases, " "),
            "áéíóúüñÁÉÍÓÚÜÑ",
            "aeiouunAEIOUUN",
        )
    )
    score = func.word_similarity(term, haystack)
    rows = await session.execute(
        select(Hotel.id, Hotel.slug, Hotel.name, Zone.slug, Zone.name)
        .join(Zone, Zone.id == Hotel.zone_id)
        .where(
            Hotel.is_active,
            Zone.is_active,
            or_(haystack.contains(term, autoescape=True), score >= MIN_SIMILARITY),
        )
        .order_by(haystack.startswith(term, autoescape=True).desc(), score.desc(), Hotel.name)
        .limit(limit)
    )
    return [
        HotelMatch(id=hotel_id, slug=slug, name=name, zone=zone, zone_name=zone_name)
        for hotel_id, slug, name, zone, zone_name in rows.tuples()
    ]


async def list_zones(session: AsyncSession) -> list[ZoneOut]:
    """Zonas activas con el precio "desde": el one way al aeropuerto más barato."""
    rows = await session.execute(
        select(Zone, func.min(Rate.price_cents))
        .outerjoin(
            Rate,
            and_(
                Rate.zone_id == Zone.id,
                Rate.is_active,
                Rate.trip_type == TripType.ONE_WAY,
                Rate.service_scope == ServiceScope.AIRPORT,
            ),
        )
        .where(Zone.is_active)
        .group_by(Zone.id)
        .order_by(Zone.sort, Zone.slug)
    )
    return [
        ZoneOut.model_validate(zone).model_copy(update={"from_price_cents": price})
        for zone, price in rows.tuples()
    ]


async def hotel_page(session: AsyncSession, slug: str) -> HotelPage | None:
    row = (
        await session.execute(
            select(Hotel, Zone)
            .join(Zone, Zone.id == Hotel.zone_id)
            .where(Hotel.slug == slug, Hotel.is_active, Zone.is_active)
        )
    ).first()
    if row is None:
        return None
    hotel, zone = row
    rates = await session.execute(
        select(VehicleClass.code, Rate.trip_type, Rate.service_scope, Rate.price_cents)
        .join(VehicleClass, VehicleClass.id == Rate.vehicle_class_id)
        .where(Rate.zone_id == zone.id, Rate.is_active, VehicleClass.is_active)
        .order_by(VehicleClass.sort, VehicleClass.max_pax, Rate.trip_type, Rate.service_scope)
    )
    return HotelPage(
        id=hotel.id,
        slug=hotel.slug,
        name=hotel.name,
        zone=ZoneOut.model_validate(zone),
        rates=[
            RateOut(vehicle_class=code, trip_type=trip, service_scope=scope, price_cents=price)
            for code, trip, scope, price in rates.tuples()
        ],
    )
