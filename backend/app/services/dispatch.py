"""Despacho por día: asignar o quitar chofer y vehículo por tramo (WORKPLAN F6.7).

El choque de horario del chofer se define con una ventana fija de dos horas alrededor del
pickup, no con la duración real del viaje: modelar la duración exacta pediría el tiempo de
manejo por zona (ya existe en `zones.drive_minutes_*`, pero combinarlo con el tráfico real y
el regreso a base es trabajo de una versión futura). Dos horas es un margen razonable para que
el mismo chofer no quede en dos tramos que se pisan, y es lo único que pide F6.7.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.models import (
    Booking,
    BookingAssignment,
    BookingLeg,
    BookingStatus,
    Driver,
    Vehicle,
    VehicleClass,
)

CONFLICT_WINDOW = timedelta(hours=2)


class DispatchError(AppError):
    status_code = 409


@dataclass
class DispatchAssignment:
    unit_index: int
    driver_id: uuid.UUID | None
    driver_name: str | None
    vehicle_id: uuid.UUID | None
    vehicle_plate: str | None


@dataclass
class DispatchLeg:
    leg_id: uuid.UUID
    booking_code: str
    leg_type: str
    pickup_time: time | None
    origin: str
    destination: str
    pax_adults: int
    pax_children: int
    vehicle_class_code: str
    vehicle_count: int
    assignments: list[DispatchAssignment] = field(default_factory=list)


async def dispatch_board(session: AsyncSession, service_date: date) -> list[DispatchLeg]:
    rows = (
        await session.execute(
            select(BookingLeg, Booking.code, VehicleClass.code)
            .join(Booking, Booking.id == BookingLeg.booking_id)
            .join(VehicleClass, VehicleClass.id == BookingLeg.vehicle_class_id)
            .where(
                BookingLeg.service_date == service_date,
                Booking.deleted_at.is_(None),
                Booking.status != BookingStatus.CANCELLED,
            )
            .order_by(BookingLeg.pickup_time)
        )
    ).all()

    leg_ids = [leg.id for leg, _, _ in rows]
    by_leg: dict[uuid.UUID, list[DispatchAssignment]] = defaultdict(list)
    if leg_ids:
        assigned = await session.execute(
            select(BookingAssignment, Driver.name, Vehicle.plate)
            .outerjoin(Driver, Driver.id == BookingAssignment.driver_id)
            .outerjoin(Vehicle, Vehicle.id == BookingAssignment.vehicle_id)
            .where(BookingAssignment.leg_id.in_(leg_ids))
        )
        for assignment, driver_name, vehicle_plate in assigned:
            by_leg[assignment.leg_id].append(
                DispatchAssignment(
                    unit_index=assignment.unit_index,
                    driver_id=assignment.driver_id,
                    driver_name=driver_name,
                    vehicle_id=assignment.vehicle_id,
                    vehicle_plate=vehicle_plate,
                )
            )

    return [
        DispatchLeg(
            leg_id=leg.id,
            booking_code=code,
            leg_type=leg.leg_type.value,
            pickup_time=leg.pickup_time,
            origin=leg.origin,
            destination=leg.destination,
            pax_adults=leg.pax_adults,
            pax_children=leg.pax_children,
            vehicle_class_code=vehicle_code,
            vehicle_count=leg.vehicle_count,
            assignments=sorted(by_leg.get(leg.id, []), key=lambda a: a.unit_index),
        )
        for leg, code, vehicle_code in rows
    ]


def _pickup_datetime(leg: BookingLeg) -> datetime:
    return datetime.combine(leg.service_date, leg.pickup_time or leg.service_time or time.min)


async def _has_driver_conflict(
    session: AsyncSession, driver_id: uuid.UUID, leg: BookingLeg
) -> bool:
    pickup = _pickup_datetime(leg)
    others = await session.scalars(
        select(BookingLeg)
        .join(BookingAssignment, BookingAssignment.leg_id == BookingLeg.id)
        .where(BookingAssignment.driver_id == driver_id, BookingLeg.id != leg.id)
    )
    return any(abs(_pickup_datetime(other) - pickup) <= CONFLICT_WINDOW for other in others)


async def assign(
    session: AsyncSession,
    leg: BookingLeg,
    admin_id: uuid.UUID,
    unit_index: int,
    driver_id: uuid.UUID | None,
    vehicle_id: uuid.UUID | None,
) -> None:
    if not 1 <= unit_index <= leg.vehicle_count:
        raise AppError("invalid_unit", f"This leg only has {leg.vehicle_count} vehicle(s).")
    if driver_id is not None and await _has_driver_conflict(session, driver_id, leg):
        raise DispatchError(
            "driver_conflict", "This driver is already assigned to an overlapping transfer."
        )
    existing = await session.scalar(
        select(BookingAssignment).where(
            BookingAssignment.leg_id == leg.id, BookingAssignment.unit_index == unit_index
        )
    )
    if existing is not None:
        existing.driver_id = driver_id
        existing.vehicle_id = vehicle_id
        existing.assigned_by_admin_id = admin_id
    else:
        session.add(
            BookingAssignment(
                leg_id=leg.id,
                unit_index=unit_index,
                driver_id=driver_id,
                vehicle_id=vehicle_id,
                assigned_by_admin_id=admin_id,
            )
        )


async def unassign(session: AsyncSession, leg: BookingLeg, unit_index: int) -> None:
    existing = await session.scalar(
        select(BookingAssignment).where(
            BookingAssignment.leg_id == leg.id, BookingAssignment.unit_index == unit_index
        )
    )
    if existing is not None:
        await session.delete(existing)
