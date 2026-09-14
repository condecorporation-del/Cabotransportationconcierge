"""Dashboard y KPIs de finanzas y marketing (WORKPLAN F6.11)."""

from datetime import date

from pydantic import BaseModel


class DashboardOut(BaseModel):
    date: date
    today_services: int
    tomorrow_services: int
    month_bookings: int
    month_revenue_cents: int
    unassigned_legs: int
    unpaid_bookings: int


class FinanceSummaryOut(BaseModel):
    revenue_30d_cents: int
    collected_30d_cents: int
    accounts_receivable_cents: int
    open_accounts: int


class MarketingKpisOut(BaseModel):
    bookings_today: int
    bookings_this_month: int
    average_booking_value_cents: int
    peak_day: date | None
    top_zone: str | None
