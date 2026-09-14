import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import select

from app.api.deps import DbSession
from app.api.v1.admin.deps import CAN_EDIT, CurrentAdmin, require_csrf
from app.core.rate_limit import rate_limit
from app.models import AdminUser, Booking, BookingLeg
from app.schemas.dispatch import AssignIn, DispatchLegOut
from app.services.dispatch import assign, dispatch_board, unassign

router = APIRouter(
    prefix="/admin/dispatch", tags=["admin-dispatch"], dependencies=[Depends(rate_limit(60))]
)
LEG_NOT_FOUND = "Leg not found."


@router.get("")
async def board_route(
    _admin: CurrentAdmin, session: DbSession, date: Annotated[date, Query()]
) -> list[DispatchLegOut]:
    legs = await dispatch_board(session, date)
    return [DispatchLegOut.model_validate(leg) for leg in legs]


async def dispatch_leg(
    leg_id: Annotated[uuid.UUID, Path()], _admin: CurrentAdmin, session: DbSession
) -> BookingLeg:
    leg = await session.scalar(
        select(BookingLeg)
        .join(Booking, Booking.id == BookingLeg.booking_id)
        .where(BookingLeg.id == leg_id, Booking.deleted_at.is_(None))
    )
    if leg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, LEG_NOT_FOUND)
    return leg


DispatchLeg = Annotated[BookingLeg, Depends(dispatch_leg)]


@router.post("/legs/{leg_id}/assign", dependencies=[Depends(require_csrf)])
async def assign_route(
    body: AssignIn,
    leg: DispatchLeg,
    admin: Annotated[AdminUser, Depends(CAN_EDIT)],
    session: DbSession,
) -> None:
    """Elegir el mismo chofer para dos tramos que se pisan (±2 h) responde 409 (F6.7)."""
    await assign(session, leg, admin.id, body.unit_index, body.driver_id, body.vehicle_id)
    await session.commit()


@router.delete(
    "/legs/{leg_id}/assign",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def unassign_route(
    leg: DispatchLeg,
    _admin: Annotated[AdminUser, Depends(CAN_EDIT)],
    session: DbSession,
    unit_index: Annotated[int, Query(ge=1, le=20)] = 1,
) -> None:
    await unassign(session, leg, unit_index)
    await session.commit()
