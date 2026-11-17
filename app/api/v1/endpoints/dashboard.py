"""老板看板接口（RBAC：仅 boss）。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentBoss, DbSession
from app.schemas.dashboard import DashboardOut
from app.services import dashboard as dashboard_service

router = APIRouter(prefix="/dashboard", tags=["经营看板"])


@router.get(
    "",
    response_model=DashboardOut,
    summary="老板看板（今日 / 本月销售额、销量 Top 5）",
    description="仅 role=boss 可访问。聚合查询全部在数据库侧完成（func.sum + group_by）。",
)
async def get_dashboard(db: DbSession, _current_boss: CurrentBoss) -> DashboardOut:
    return await dashboard_service.get_dashboard(db)
