"""Dashboard y KPIs de finanzas y marketing (WORKPLAN F6.11): consultas agregadas indexadas.

Los rangos de fecha se comparan como `>= inicio AND < fin` en vez de `func.date(...) = x`, para
que Postgres pueda usar los índices existentes (`ix_bookings_company_status_created`,
`ix_booking_legs_company_service_date`) en lugar de calcular una función sobre cada fila.
"""

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AccountCharge,
    AccountPayment,
    AccountStatus,
    Booking,
    BookingAssignment,
    BookingLeg,
    BookingStatus,
    ChargeStatus,
    ClientAccount,
    Hotel,
    Payment,
    PaymentStatus,
    Zone,
)
from app.schemas.dashboard import DashboardOut, FinanceSummaryOut, MarketingKpisOut


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, UTC)
    return start, start + timedelta(days=1)


async def dashboard_summary(session: AsyncSession, on_date: date) -> DashboardOut:
    tomorrow = on_date + timedelta(days=1)
    month_start, _ = _day_bounds(on_date.replace(day=1))

    rows = await session.execute(
        select(BookingLeg.service_date, func.count())
        .join(Booking, Booking.id == BookingLeg.booking_id)
        .where(
            BookingLeg.service_date.in_((on_date, tomorrow)),
            Booking.status != BookingStatus.CANCELLED,
            Booking.deleted_at.is_(None),
        )
        .group_by(BookingLeg.service_date)
    )
    per_day: dict[date, int] = {row[0]: row[1] for row in rows}

    month_bookings, month_revenue_cents = (
        await session.execute(
            select(func.count(), func.coalesce(func.sum(Booking.total_cents), 0)).where(
                Booking.created_at >= month_start,
                Booking.status != BookingStatus.CANCELLED,
                Booking.deleted_at.is_(None),
            )
        )
    ).one()

    unassigned_legs = await session.scalar(
        select(func.count(func.distinct(BookingLeg.id)))
        .select_from(BookingLeg)
        .join(Booking, Booking.id == BookingLeg.booking_id)
        .outerjoin(BookingAssignment, BookingAssignment.leg_id == BookingLeg.id)
        .where(
            BookingLeg.service_date.in_((on_date, tomorrow)),
            Booking.status != BookingStatus.CANCELLED,
            Booking.deleted_at.is_(None),
            BookingAssignment.id.is_(None),
        )
    )

    unpaid_bookings = await session.scalar(
        select(func.count()).where(
            Booking.status == BookingStatus.PENDING_PAYMENT, Booking.deleted_at.is_(None)
        )
    )

    return DashboardOut(
        date=on_date,
        today_services=per_day.get(on_date, 0),
        tomorrow_services=per_day.get(tomorrow, 0),
        month_bookings=month_bookings,
        month_revenue_cents=int(month_revenue_cents),
        unassigned_legs=unassigned_legs or 0,
        unpaid_bookings=unpaid_bookings or 0,
    )


async def finance_summary(session: AsyncSession) -> FinanceSummaryOut:
    since = datetime.now(UTC) - timedelta(days=30)
    revenue_30d = await session.scalar(
        select(func.coalesce(func.sum(Booking.total_cents), 0)).where(
            Booking.created_at >= since,
            Booking.status != BookingStatus.CANCELLED,
            Booking.deleted_at.is_(None),
        )
    )
    collected_30d = await session.scalar(
        select(func.coalesce(func.sum(Payment.amount_cents), 0)).where(
            Payment.status == PaymentStatus.SUCCEEDED, Payment.paid_at >= since
        )
    )
    charged = await session.scalar(
        select(func.coalesce(func.sum(AccountCharge.amount_cents), 0)).where(
            AccountCharge.status != ChargeStatus.VOID
        )
    )
    paid = await session.scalar(select(func.coalesce(func.sum(AccountPayment.amount_cents), 0)))
    open_accounts = await session.scalar(
        select(func.count()).where(ClientAccount.status == AccountStatus.OPEN)
    )
    return FinanceSummaryOut(
        revenue_30d_cents=int(revenue_30d or 0),
        collected_30d_cents=int(collected_30d or 0),
        accounts_receivable_cents=int(charged or 0) - int(paid or 0),
        open_accounts=open_accounts or 0,
    )


async def marketing_kpis(session: AsyncSession, today: date) -> MarketingKpisOut:
    day_start, day_end = _day_bounds(today)
    month_start, _ = _day_bounds(today.replace(day=1))

    bookings_today = await session.scalar(
        select(func.count()).where(
            Booking.created_at >= day_start,
            Booking.created_at < day_end,
            Booking.deleted_at.is_(None),
        )
    )

    bookings_this_month, average_booking_value_cents = (
        await session.execute(
            select(func.count(), func.coalesce(func.avg(Booking.total_cents), 0)).where(
                Booking.created_at >= month_start,
                Booking.status != BookingStatus.CANCELLED,
                Booking.deleted_at.is_(None),
            )
        )
    ).one()

    peak_row = (
        await session.execute(
            select(func.date(Booking.created_at).label("day"), func.count().label("bookings"))
            .where(Booking.created_at >= month_start, Booking.deleted_at.is_(None))
            .group_by("day")
            .order_by(func.count().desc())
            .limit(1)
        )
    ).first()

    zone_row = (
        await session.execute(
            select(Zone.slug, func.count().label("bookings"))
            .select_from(BookingLeg)
            .join(Booking, Booking.id == BookingLeg.booking_id)
            .join(Hotel, Hotel.id == BookingLeg.hotel_id)
            .join(Zone, Zone.id == Hotel.zone_id)
            .where(
                Booking.created_at >= month_start,
                Booking.status != BookingStatus.CANCELLED,
                Booking.deleted_at.is_(None),
            )
            .group_by(Zone.slug)
            .order_by(func.count().desc())
            .limit(1)
        )
    ).first()

    return MarketingKpisOut(
        bookings_today=bookings_today or 0,
        bookings_this_month=bookings_this_month,
        average_booking_value_cents=int(average_booking_value_cents),
        peak_day=peak_row[0] if peak_row else None,
        top_zone=zone_row[0] if zone_row else None,
    )
