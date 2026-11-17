"""老板看板服务：今日 / 本月销售额与销量 Top 5。

时区策略：数据库统一存储 UTC；统计时先在业务时区（默认 Asia/Shanghai）
计算自然日 / 自然月边界，再转换为 UTC 进行查询，保证跨时区数据口径正确。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.money import money
from app.crud import dashboard as crud_dashboard
from app.schemas.dashboard import DashboardOut, TopPartOut


def _period_bounds() -> tuple[datetime, datetime, datetime, datetime]:
    """返回 UTC naive 的 [今日开始, 明日开始, 本月开始, 下月开始)。"""
    tz = settings.tzinfo
    now_local = datetime.now(UTC).astimezone(tz)
    today: date = now_local.date()

    today_start_local = datetime.combine(today, time.min, tzinfo=tz)
    tomorrow_start_local = datetime.combine(today + timedelta(days=1), time.min, tzinfo=tz)

    month_start_day = today.replace(day=1)
    next_month_day = date(today.year + 1, 1, 1) if today.month == 12 else date(today.year, today.month + 1, 1)
    month_start_local = datetime.combine(month_start_day, time.min, tzinfo=tz)
    next_month_local = datetime.combine(next_month_day, time.min, tzinfo=tz)

    def to_utc_naive(value: datetime) -> datetime:
        return value.astimezone(UTC).replace(tzinfo=None)

    return (
        to_utc_naive(today_start_local),
        to_utc_naive(tomorrow_start_local),
        to_utc_naive(month_start_local),
        to_utc_naive(next_month_local),
    )


async def get_dashboard(db: AsyncSession) -> DashboardOut:
    today_start, tomorrow_start, month_start, next_month_start = _period_bounds()

    today_amount, today_count = await crud_dashboard.sales_summary(
        db, start=today_start, end=tomorrow_start
    )
    month_amount, month_count = await crud_dashboard.sales_summary(
        db, start=month_start, end=next_month_start
    )
    top_rows = await crud_dashboard.top_selling_parts(
        db, start=month_start, end=next_month_start, limit=5
    )

    return DashboardOut(
        today_sales_amount=money(today_amount),
        month_sales_amount=money(month_amount),
        today_order_count=today_count,
        month_order_count=month_count,
        top_parts=[
            TopPartOut(part_id=part_id, part_name=part_name, quantity=quantity)
            for part_id, part_name, quantity in top_rows
        ],
        generated_at=datetime.now(UTC),
    )
