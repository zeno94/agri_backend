"""管理员看板接口（RBAC：仅 boss）。"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import CurrentBoss, DbSession, require_module
from app.schemas.dashboard import DashboardOut, DashboardReportOut
from app.services import audit as audit_service
from app.services import dashboard as dashboard_service

router = APIRouter(prefix="/dashboard", tags=["经营看板"], dependencies=[Depends(require_module("dashboard"))])


@router.get(
    "/report",
    response_model=DashboardReportOut,
    summary="经营报表（按日期区间）",
    description=(
        "仅 role=boss 可访问。销售、采购、毛利、客户/供应商排行、分类占比与趋势"
        "全部在数据库侧聚合；日期按业务时区（默认 Asia/Shanghai）自然日计算。"
    ),
)
async def get_dashboard_report(
    request: Request,
    db: DbSession,
    current_boss: CurrentBoss,
    start_date: Annotated[date | None, Query(description="开始日期（含，Asia/Shanghai）")] = None,
    end_date: Annotated[date | None, Query(description="结束日期（含，Asia/Shanghai）")] = None,
) -> DashboardReportOut:
    result = await dashboard_service.get_report(db, start_date=start_date, end_date=end_date)
    await audit_service.record(
        db,
        user=current_boss,
        action="dashboard.view",
        module="dashboard",
        method="GET",
        path=request.url.path,
        detail={
            "report": True,
            "start_date": result.start_date.isoformat(),
            "end_date": result.end_date.isoformat(),
            "sales_amount": result.sales_amount,
            "purchase_amount": result.purchase_amount,
            "gross_profit": result.gross_profit,
        },
        request=request,
    )
    return result


@router.get(
    "",
    response_model=DashboardOut,
    summary="管理员看板（今日 / 本月销售额、销量 Top 5）",
    description="仅 role=boss 可访问。聚合查询全部在数据库侧完成（func.sum + group_by）。",
)
async def get_dashboard(
    request: Request,
    db: DbSession,
    current_boss: CurrentBoss,
) -> DashboardOut:
    result = await dashboard_service.get_dashboard(db)
    await audit_service.record(
        db,
        user=current_boss,
        action="dashboard.view",
        module="dashboard",
        method="GET",
        path=request.url.path,
        detail={
            "today_sales_amount": result.today_sales_amount,
            "month_sales_amount": result.month_sales_amount,
            "today_order_count": result.today_order_count,
            "month_order_count": result.month_order_count,
        },
        request=request,
    )
    return result
