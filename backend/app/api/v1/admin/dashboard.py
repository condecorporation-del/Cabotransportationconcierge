from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import DbSession
from app.api.v1.admin.deps import CurrentAdmin
from app.core.rate_limit import rate_limit
from app.schemas.dashboard import DashboardOut, FinanceSummaryOut, MarketingKpisOut
from app.services.dashboard import dashboard_summary, finance_summary, marketing_kpis

router = APIRouter(tags=["admin-dashboard"], dependencies=[Depends(rate_limit(60))])


@router.get("/admin/dashboard")
async def dashboard_route(
    _admin: CurrentAdmin, session: DbSession, date: Annotated[date, Query()]
) -> DashboardOut:
    return await dashboard_summary(session, date)


@router.get("/admin/finance/summary")
async def finance_summary_route(_admin: CurrentAdmin, session: DbSession) -> FinanceSummaryOut:
    return await finance_summary(session)


@router.get("/admin/marketing/kpis")
async def marketing_kpis_route(_admin: CurrentAdmin, session: DbSession) -> MarketingKpisOut:
    # UTC, no la fecha local del servidor: `Booking.created_at` también es UTC (§8, TimestampMixin).
    return await marketing_kpis(session, datetime.now(UTC).date())
