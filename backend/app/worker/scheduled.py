"""Trabajos programados del correo (F5.7, F5.8): recordatorio 24 h antes y reseña después.

No hay cron, Celery ni APScheduler: es el mismo patrón que `send_emails.py` (F5.1) — un módulo
con `run_once()` que se corre suelto o con `--loop`. Nada se envía desde aquí; ambos trabajos
solo encolan en `email_outbox`, y el worker de F5.1 sigue siendo el único que habla con Resend.

Cada trabajo marca su fila al encolar (`booking_legs.reminder_sent_at`,
`bookings.review_requested_at`), así que dos corridas seguidas —o dos procesos a la vez— no
mandan el mismo correo dos veces.

uv run python -m app.worker.scheduled            # una pasada y sale
uv run python -m app.worker.scheduled --loop     # se queda corriendo (producción)
"""

import argparse
import asyncio
import uuid
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.security import booking_manage_url
from app.db import engine_from_url
from app.models import (
    Booking,
    BookingAssignment,
    BookingLeg,
    BookingStatus,
    Company,
    CompanySettings,
    Customer,
    Driver,
    LegStatus,
    Vehicle,
)
from app.services.email import enqueue

REMINDER_HOURS = 24
# Margen después de la recogida antes de pedir reseña: el viaje tiene que haber terminado.
REVIEW_DELAY_HOURS = 4
# Al encender el trabajo por primera vez no se le pide reseña a medio año de clientes viejos.
REVIEW_MAX_AGE_DAYS = 30
# Un tramo sin hora de recogida (salida por confirmar) se trata como mediodía.
ASSUMED_PICKUP = time(12, 0)
# Un viaje cancelado no lleva recordatorio ni reseña; uno sin pagar todavía tampoco.
LIVE_STATUSES = (BookingStatus.CONFIRMED, BookingStatus.PAID, BookingStatus.COMPLETED)
SLEEP_SECONDS = 900


def pickup_at(leg: BookingLeg, timezone: str) -> datetime:
    """La recogida está en hora local de la empresa y `now` es UTC. Sin convertir, el
    recordatorio saldría con el desfase del huso (7 h en Los Cabos) metido dentro."""
    return datetime.combine(leg.service_date, leg.pickup_time or ASSUMED_PICKUP).replace(
        tzinfo=ZoneInfo(timezone)
    )


async def crew_by_leg(session: AsyncSession, leg_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Chofer y vehículo de cada unidad, en una sola consulta para todos los tramos. Un tramo
    sin asignar todavía no aparece en el resultado."""
    rows = await session.execute(
        select(BookingAssignment.leg_id, Driver.name, Vehicle.make, Vehicle.model, Vehicle.plate)
        .outerjoin(Driver, Driver.id == BookingAssignment.driver_id)
        .outerjoin(Vehicle, Vehicle.id == BookingAssignment.vehicle_id)
        .where(BookingAssignment.leg_id.in_(leg_ids))
        .order_by(BookingAssignment.unit_index)
    )
    units: dict[uuid.UUID, list[str]] = {}
    for leg_id, driver, make, model, plate in rows:
        vehicle = f"{make} {model} ({plate})" if plate else None
        detail = " · ".join(part for part in (driver, vehicle) if part)
        if detail:
            units.setdefault(leg_id, []).append(detail)
    return {leg_id: " / ".join(details) for leg_id, details in units.items()}


async def send_reminders(session: AsyncSession, now: datetime) -> int:
    """F5.7: un recordatorio por tramo, dentro de las 24 h previas a la recogida."""
    rows = (
        await session.execute(
            select(BookingLeg, Booking, Company, Customer)
            .join(Booking, Booking.id == BookingLeg.booking_id)
            .join(Company, Company.id == BookingLeg.company_id)
            .join(Customer, Customer.id == Booking.customer_id)
            .where(
                BookingLeg.reminder_sent_at.is_(None),
                BookingLeg.status == LegStatus.SCHEDULED,
                Booking.status.in_(LIVE_STATUSES),
                Booking.deleted_at.is_(None),
                # Filtro amplio en SQL (cualquier huso cabe de sobra en un día); la hora
                # exacta se decide abajo, ya con la zona horaria de cada empresa.
                BookingLeg.service_date >= now.date(),
                BookingLeg.service_date <= now.date() + timedelta(days=2),
            )
        )
    ).all()
    due = [
        (leg, booking, customer)
        for leg, booking, company, customer in rows
        if pickup_at(leg, company.timezone) - timedelta(hours=REMINDER_HOURS)
        <= now
        < pickup_at(leg, company.timezone)
    ]
    crew = await crew_by_leg(session, [leg.id for leg, _, _ in due]) if due else {}
    for leg, booking, customer in due:
        await enqueue(
            session,
            company_id=booking.company_id,
            template="booking_reminder",
            to=[customer.email],
            language=booking.language,
            booking_id=booking.id,
            context={
                "code": booking.code,
                "service_date": leg.service_date.isoformat(),
                "pickup_time": leg.pickup_time.strftime("%H:%M") if leg.pickup_time else None,
                "origin": leg.origin,
                "destination": leg.destination,
                "crew": crew.get(leg.id),
                "manage_url": booking_manage_url(booking.company_id, booking.code),
            },
        )
        leg.reminder_sent_at = now
    return len(due)


async def request_reviews(session: AsyncSession, now: datetime) -> int:
    """F5.8: una sola petición por reserva, unas horas después del último tramo."""
    rows = (
        await session.execute(
            select(Booking, Company, CompanySettings, Customer)
            .join(Company, Company.id == Booking.company_id)
            .join(CompanySettings, CompanySettings.company_id == Booking.company_id)
            .join(Customer, Customer.id == Booking.customer_id)
            .where(
                Booking.review_requested_at.is_(None),
                Booking.status.in_(LIVE_STATUSES),
                Booking.deleted_at.is_(None),
                # Sin esta cota el trabajo re-escanearía para siempre cada reserva vieja que
                # nunca llegó a marcarse (por ejemplo, las de antes de configurar el enlace).
                exists().where(
                    BookingLeg.booking_id == Booking.id,
                    BookingLeg.service_date >= now.date() - timedelta(days=REVIEW_MAX_AGE_DAYS + 1),
                    BookingLeg.service_date <= now.date(),
                ),
            )
            .options(selectinload(Booking.legs))
        )
    ).all()
    sent = 0
    for booking, company, settings, customer in rows:
        legs = [leg for leg in booking.legs if leg.status != LegStatus.CANCELLED]
        review_url = (settings.social_links or {}).get("google_review")
        if not legs or not review_url:
            # Sin tramos vivos no hubo viaje; sin enlace, el correo no tendría a dónde mandar al
            # cliente. En los dos casos la reserva se deja sin marcar para que salga sola
            # después, en cuanto el admin configure el enlace.
            continue
        ended = max(pickup_at(leg, company.timezone) for leg in legs)
        due = ended + timedelta(hours=REVIEW_DELAY_HOURS)
        if not due <= now <= due + timedelta(days=REVIEW_MAX_AGE_DAYS):
            continue
        await enqueue(
            session,
            company_id=booking.company_id,
            template="review_request",
            to=[customer.email],
            language=booking.language,
            booking_id=booking.id,
            context={"code": booking.code, "review_url": review_url},
        )
        booking.review_requested_at = now
        sent += 1
    return sent


async def run_once(session: AsyncSession, now: datetime | None = None) -> tuple[int, int]:
    """`now` explícito en vez de congelar el reloj: la prueba de F5.7 mueve la hora sin
    depender de una librería que parchea `datetime` por debajo del driver async."""
    now = now or datetime.now(UTC)
    reminders = await send_reminders(session, now)
    reviews = await request_reviews(session, now)
    await session.commit()
    return reminders, reviews


async def _main(loop: bool) -> None:
    engine = engine_from_url(get_settings().database_url, pooled=False)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        while True:
            async with sessionmaker() as session:
                await run_once(session)
            if not loop:
                break
            await asyncio.sleep(SLEEP_SECONDS)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--loop", action="store_true", help="corre indefinidamente (producción)")
    asyncio.run(_main(parser.parse_args().loop))
