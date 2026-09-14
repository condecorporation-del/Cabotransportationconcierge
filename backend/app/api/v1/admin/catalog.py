import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentCompany, DbSession
from app.api.v1.admin.deps import CAN_EDIT_CATALOG, CurrentAdmin, require_csrf
from app.core.rate_limit import rate_limit
from app.models import (
    Activity,
    ActivityPackage,
    AdminUser,
    CompanySettings,
    Extra,
    Hotel,
    Promotion,
    Rate,
    Zone,
)
from app.schemas.catalog_admin import (
    ActivityIn,
    ActivityOut,
    ActivityPackageIn,
    ActivityPackageOut,
    ActivityPackagePatch,
    ActivityPatch,
    CompanySettingsOut,
    CompanySettingsPatch,
    ExtraIn,
    ExtraOut,
    ExtraPatch,
    HotelIn,
    HotelOut,
    HotelPatch,
    PromotionIn,
    PromotionOut,
    PromotionPatch,
    RateIn,
    RateOut,
    RatePatch,
    ZoneIn,
    ZoneOut,
    ZonePatch,
)

router = APIRouter(tags=["admin-catalog"], dependencies=[Depends(rate_limit(60))])
NOT_FOUND = "Not found."


@router.get("/admin/zones")
async def list_zones(_admin: CurrentAdmin, session: DbSession) -> list[ZoneOut]:
    rows = (await session.scalars(select(Zone).order_by(Zone.sort))).all()
    return [ZoneOut.model_validate(row) for row in rows]


@router.post(
    "/admin/zones", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)]
)
async def create_zone(
    body: ZoneIn, _admin: Annotated[AdminUser, Depends(CAN_EDIT_CATALOG)], session: DbSession
) -> ZoneOut:
    zone = Zone(**body.model_dump())
    session.add(zone)
    await session.commit()
    return ZoneOut.model_validate(zone)


@router.patch("/admin/zones/{zone_id}", dependencies=[Depends(require_csrf)])
async def patch_zone(
    zone_id: uuid.UUID,
    body: ZonePatch,
    _admin: Annotated[AdminUser, Depends(CAN_EDIT_CATALOG)],
    session: DbSession,
) -> ZoneOut:
    zone = await session.get(Zone, zone_id)
    if zone is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(zone, key, value)
    await session.commit()
    return ZoneOut.model_validate(zone)


@router.get("/admin/hotels")
async def list_hotels(_admin: CurrentAdmin, session: DbSession) -> list[HotelOut]:
    rows = (await session.scalars(select(Hotel).order_by(Hotel.name))).all()
    return [HotelOut.model_validate(row) for row in rows]


@router.post(
    "/admin/hotels", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)]
)
async def create_hotel(
    body: HotelIn, _admin: Annotated[AdminUser, Depends(CAN_EDIT_CATALOG)], session: DbSession
) -> HotelOut:
    hotel = Hotel(**body.model_dump())
    session.add(hotel)
    await session.commit()
    return HotelOut.model_validate(hotel)


@router.patch("/admin/hotels/{hotel_id}", dependencies=[Depends(require_csrf)])
async def patch_hotel(
    hotel_id: uuid.UUID,
    body: HotelPatch,
    _admin: Annotated[AdminUser, Depends(CAN_EDIT_CATALOG)],
    session: DbSession,
) -> HotelOut:
    hotel = await session.get(Hotel, hotel_id)
    if hotel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(hotel, key, value)
    await session.commit()
    return HotelOut.model_validate(hotel)


@router.get("/admin/rates")
async def list_rates(_admin: CurrentAdmin, session: DbSession) -> list[RateOut]:
    rows = (await session.scalars(select(Rate))).all()
    return [RateOut.model_validate(row) for row in rows]


@router.post(
    "/admin/rates", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)]
)
async def create_rate(
    body: RateIn, _admin: Annotated[AdminUser, Depends(CAN_EDIT_CATALOG)], session: DbSession
) -> RateOut:
    rate = Rate(**body.model_dump())
    session.add(rate)
    await session.commit()
    return RateOut.model_validate(rate)


@router.patch("/admin/rates/{rate_id}", dependencies=[Depends(require_csrf)])
async def patch_rate(
    rate_id: uuid.UUID,
    body: RatePatch,
    _admin: Annotated[AdminUser, Depends(CAN_EDIT_CATALOG)],
    session: DbSession,
) -> RateOut:
    """Editar el precio de una tarifa (F6.10, F6.12): queda auditada por `AUDITED_MODELS`."""
    rate = await session.get(Rate, rate_id)
    if rate is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(rate, key, value)
    await session.commit()
    return RateOut.model_validate(rate)


@router.get("/admin/extras")
async def list_extras(_admin: CurrentAdmin, session: DbSession) -> list[ExtraOut]:
    rows = (await session.scalars(select(Extra).order_by(Extra.sort))).all()
    return [ExtraOut.model_validate(row) for row in rows]


@router.post(
    "/admin/extras", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)]
)
async def create_extra(
    body: ExtraIn, _admin: Annotated[AdminUser, Depends(CAN_EDIT_CATALOG)], session: DbSession
) -> ExtraOut:
    extra = Extra(**body.model_dump())
    session.add(extra)
    await session.commit()
    return ExtraOut.model_validate(extra)


@router.patch("/admin/extras/{extra_id}", dependencies=[Depends(require_csrf)])
async def patch_extra(
    extra_id: uuid.UUID,
    body: ExtraPatch,
    _admin: Annotated[AdminUser, Depends(CAN_EDIT_CATALOG)],
    session: DbSession,
) -> ExtraOut:
    extra = await session.get(Extra, extra_id)
    if extra is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(extra, key, value)
    await session.commit()
    return ExtraOut.model_validate(extra)


@router.get("/admin/activities")
async def list_activities(_admin: CurrentAdmin, session: DbSession) -> list[ActivityOut]:
    rows = (await session.scalars(select(Activity).order_by(Activity.slug))).all()
    return [ActivityOut.model_validate(row) for row in rows]


@router.post(
    "/admin/activities", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)]
)
async def create_activity(
    body: ActivityIn, _admin: Annotated[AdminUser, Depends(CAN_EDIT_CATALOG)], session: DbSession
) -> ActivityOut:
    activity = Activity(**body.model_dump())
    session.add(activity)
    await session.commit()
    return ActivityOut.model_validate(activity)


@router.patch("/admin/activities/{activity_id}", dependencies=[Depends(require_csrf)])
async def patch_activity(
    activity_id: uuid.UUID,
    body: ActivityPatch,
    _admin: Annotated[AdminUser, Depends(CAN_EDIT_CATALOG)],
    session: DbSession,
) -> ActivityOut:
    activity = await session.get(Activity, activity_id)
    if activity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(activity, key, value)
    await session.commit()
    return ActivityOut.model_validate(activity)


@router.get("/admin/packages")
async def list_packages(_admin: CurrentAdmin, session: DbSession) -> list[ActivityPackageOut]:
    rows = (await session.scalars(select(ActivityPackage).order_by(ActivityPackage.slug))).all()
    return [ActivityPackageOut.model_validate(row) for row in rows]


@router.post(
    "/admin/packages", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)]
)
async def create_package(
    body: ActivityPackageIn,
    _admin: Annotated[AdminUser, Depends(CAN_EDIT_CATALOG)],
    session: DbSession,
) -> ActivityPackageOut:
    package = ActivityPackage(**body.model_dump())
    session.add(package)
    await session.commit()
    return ActivityPackageOut.model_validate(package)


@router.patch("/admin/packages/{package_id}", dependencies=[Depends(require_csrf)])
async def patch_package(
    package_id: uuid.UUID,
    body: ActivityPackagePatch,
    _admin: Annotated[AdminUser, Depends(CAN_EDIT_CATALOG)],
    session: DbSession,
) -> ActivityPackageOut:
    package = await session.get(ActivityPackage, package_id)
    if package is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(package, key, value)
    await session.commit()
    return ActivityPackageOut.model_validate(package)


@router.get("/admin/promotions")
async def list_promotions(_admin: CurrentAdmin, session: DbSession) -> list[PromotionOut]:
    rows = (await session.scalars(select(Promotion))).all()
    return [PromotionOut.model_validate(row) for row in rows]


@router.post(
    "/admin/promotions", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)]
)
async def create_promotion(
    body: PromotionIn, _admin: Annotated[AdminUser, Depends(CAN_EDIT_CATALOG)], session: DbSession
) -> PromotionOut:
    promotion = Promotion(**body.model_dump())
    session.add(promotion)
    await session.commit()
    return PromotionOut.model_validate(promotion)


@router.patch("/admin/promotions/{promotion_id}", dependencies=[Depends(require_csrf)])
async def patch_promotion(
    promotion_id: uuid.UUID,
    body: PromotionPatch,
    _admin: Annotated[AdminUser, Depends(CAN_EDIT_CATALOG)],
    session: DbSession,
) -> PromotionOut:
    promotion = await session.get(Promotion, promotion_id)
    if promotion is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(promotion, key, value)
    await session.commit()
    return PromotionOut.model_validate(promotion)


@router.get("/admin/settings")
async def get_settings_route(
    _admin: CurrentAdmin, company: CurrentCompany, session: DbSession
) -> CompanySettingsOut:
    settings = await session.get(CompanySettings, company.id)
    if settings is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return CompanySettingsOut.model_validate(settings)


@router.patch("/admin/settings", dependencies=[Depends(require_csrf)])
async def patch_settings_route(
    body: CompanySettingsPatch,
    company: CurrentCompany,
    _admin: Annotated[AdminUser, Depends(CAN_EDIT_CATALOG)],
    session: DbSession,
) -> CompanySettingsOut:
    settings = await session.get(CompanySettings, company.id)
    if settings is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(settings, key, value)
    await session.commit()
    return CompanySettingsOut.model_validate(settings)
