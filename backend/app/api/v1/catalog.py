from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status
from sqlalchemy import select

from app.api.deps import DbSession, cached_json, get_company
from app.core.rate_limit import rate_limit
from app.models import Activity, ActivityPackage, Extra, VehicleClass
from app.schemas.catalog import (
    ActivityOut,
    ExtraOut,
    HotelMatch,
    HotelPage,
    PackageOut,
    VehicleOut,
    ZoneOut,
)
from app.services import catalog

router = APIRouter(
    prefix="/catalog",
    tags=["catalog"],
    dependencies=[Depends(rate_limit(120)), Depends(get_company)],
)


@router.get("/zones", response_model=list[ZoneOut])
async def zones(request: Request, session: DbSession) -> Response:
    return cached_json(request, list[ZoneOut], await catalog.list_zones(session))


@router.get("/hotels", response_model=list[HotelMatch])
async def hotels(
    request: Request, session: DbSession, q: Annotated[str, Query(max_length=60)]
) -> Response:
    return cached_json(request, list[HotelMatch], await catalog.search_hotels(session, q))


@router.get("/hotels/{slug}", response_model=HotelPage)
async def hotel(
    request: Request, session: DbSession, slug: Annotated[str, Path(max_length=120)]
) -> Response:
    page = await catalog.hotel_page(session, slug)
    if page is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hotel not found.")
    return cached_json(request, HotelPage, page)


async def _active(session: DbSession, model: Any, *order: Any) -> list[Any]:
    return list(
        (await session.scalars(select(model).where(model.is_active).order_by(*order))).all()
    )


@router.get("/vehicles", response_model=list[VehicleOut])
async def vehicles(request: Request, session: DbSession) -> Response:
    rows = await _active(session, VehicleClass, VehicleClass.sort, VehicleClass.max_pax)
    return cached_json(request, list[VehicleOut], rows)


@router.get("/extras", response_model=list[ExtraOut])
async def extras(request: Request, session: DbSession) -> Response:
    rows = await _active(session, Extra, Extra.sort, Extra.code)
    return cached_json(request, list[ExtraOut], rows)


@router.get("/activities", response_model=list[ActivityOut])
async def activities(request: Request, session: DbSession) -> Response:
    rows = await _active(session, Activity, Activity.slug)
    return cached_json(request, list[ActivityOut], rows)


@router.get("/packages", response_model=list[PackageOut])
async def packages(request: Request, session: DbSession) -> Response:
    rows = await _active(session, ActivityPackage, ActivityPackage.activity_count)
    return cached_json(request, list[PackageOut], rows)
