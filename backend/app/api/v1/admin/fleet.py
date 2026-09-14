import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import DbSession
from app.api.v1.admin.deps import CAN_EDIT, CurrentAdmin, require_csrf
from app.core.rate_limit import rate_limit
from app.models import AdminUser, Driver, Vehicle, VehicleClass
from app.schemas.fleet import (
    DriverIn,
    DriverOut,
    DriverPatch,
    VehicleClassIn,
    VehicleClassOut,
    VehicleClassPatch,
    VehicleIn,
    VehicleOut,
    VehiclePatch,
)

router = APIRouter(tags=["admin-fleet"], dependencies=[Depends(rate_limit(60))])
NOT_FOUND = "Not found."


@router.get("/admin/drivers")
async def list_drivers(_admin: CurrentAdmin, session: DbSession) -> list[DriverOut]:
    rows = (await session.scalars(select(Driver).order_by(Driver.name))).all()
    return [DriverOut.model_validate(row) for row in rows]


@router.post(
    "/admin/drivers", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)]
)
async def create_driver(
    body: DriverIn, _admin: Annotated[AdminUser, Depends(CAN_EDIT)], session: DbSession
) -> DriverOut:
    driver = Driver(**body.model_dump())
    session.add(driver)
    await session.commit()
    return DriverOut.model_validate(driver)


@router.patch("/admin/drivers/{driver_id}", dependencies=[Depends(require_csrf)])
async def patch_driver(
    driver_id: uuid.UUID,
    body: DriverPatch,
    _admin: Annotated[AdminUser, Depends(CAN_EDIT)],
    session: DbSession,
) -> DriverOut:
    driver = await session.get(Driver, driver_id)
    if driver is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(driver, key, value)
    await session.commit()
    return DriverOut.model_validate(driver)


@router.get("/admin/vehicles")
async def list_vehicles(_admin: CurrentAdmin, session: DbSession) -> list[VehicleOut]:
    rows = (await session.scalars(select(Vehicle).order_by(Vehicle.plate))).all()
    return [VehicleOut.model_validate(row) for row in rows]


@router.post(
    "/admin/vehicles", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)]
)
async def create_vehicle(
    body: VehicleIn, _admin: Annotated[AdminUser, Depends(CAN_EDIT)], session: DbSession
) -> VehicleOut:
    vehicle = Vehicle(**body.model_dump())
    session.add(vehicle)
    await session.commit()
    return VehicleOut.model_validate(vehicle)


@router.patch("/admin/vehicles/{vehicle_id}", dependencies=[Depends(require_csrf)])
async def patch_vehicle(
    vehicle_id: uuid.UUID,
    body: VehiclePatch,
    _admin: Annotated[AdminUser, Depends(CAN_EDIT)],
    session: DbSession,
) -> VehicleOut:
    vehicle = await session.get(Vehicle, vehicle_id)
    if vehicle is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(vehicle, key, value)
    await session.commit()
    return VehicleOut.model_validate(vehicle)


@router.get("/admin/vehicle-classes")
async def list_vehicle_classes(_admin: CurrentAdmin, session: DbSession) -> list[VehicleClassOut]:
    rows = (await session.scalars(select(VehicleClass).order_by(VehicleClass.sort))).all()
    return [VehicleClassOut.model_validate(row) for row in rows]


@router.post(
    "/admin/vehicle-classes",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_vehicle_class(
    body: VehicleClassIn, _admin: Annotated[AdminUser, Depends(CAN_EDIT)], session: DbSession
) -> VehicleClassOut:
    vehicle_class = VehicleClass(**body.model_dump())
    session.add(vehicle_class)
    await session.commit()
    return VehicleClassOut.model_validate(vehicle_class)


@router.patch("/admin/vehicle-classes/{vehicle_class_id}", dependencies=[Depends(require_csrf)])
async def patch_vehicle_class(
    vehicle_class_id: uuid.UUID,
    body: VehicleClassPatch,
    _admin: Annotated[AdminUser, Depends(CAN_EDIT)],
    session: DbSession,
) -> VehicleClassOut:
    vehicle_class = await session.get(VehicleClass, vehicle_class_id)
    if vehicle_class is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(vehicle_class, key, value)
    await session.commit()
    return VehicleClassOut.model_validate(vehicle_class)
