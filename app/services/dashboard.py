"""管理员看板服务：今日 / 本月概览，以及按日期区间聚合的经营报表。

时区策略：数据库统一存储 UTC；统计时先在业务时区（默认 Asia/Shanghai）
计算自然日 / 自然月边界，再转换为 UTC 进行查询，保证跨时区数据口径正确。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.money import money
from app.core.time import local_day_end_exclusive, local_day_start, to_local_date
from app.crud import dashboard as crud_dashboard
from app.schemas.dashboard import (
    CategorySalesOut,
    DashboardOut,
    DashboardReportOut,
    ReportPartOut,
    TopCustomerOut,
    TopPartOut,
    TopSupplierOut,
    TrendPointOut,
)


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

    today_amount, today_count = await crud_dashboard.sales_summary(db, start=today_start, end=tomorrow_start)
    month_amount, month_count = await crud_dashboard.sales_summary(db, start=month_start, end=next_month_start)
    top_rows = await crud_dashboard.top_selling_parts(db, start=month_start, end=next_month_start, limit=5)

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


def _resolve_range(start_date: date | None, end_date: date | None) -> tuple[date, date]:
    """解析报表日期区间；缺省为最近 90 天（含今天）。"""
    today = datetime.now(UTC).astimezone(settings.tzinfo).date()

    if start_date is None and end_date is None:
        end_date = today
        start_date = end_date - timedelta(days=89)
    elif start_date is None:
        start_date = end_date - timedelta(days=29)
    elif end_date is None:
        end_date = today

    if start_date > end_date:
        raise AppError("INVALID_DATE_RANGE", "开始日期不能晚于结束日期", 400)
    return start_date, end_date


def _is_month_range(start_date: date, end_date: date) -> bool:
    """区间超过约一个季度时按月展示趋势，避免折线过密。"""
    return (end_date - start_date).days > 92


async def get_report(
    db: AsyncSession,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> DashboardReportOut:
    start_date, end_date = _resolve_range(start_date, end_date)
    start = local_day_start(start_date)
    end = local_day_end_exclusive(end_date)

    sales_amount, sales_orders = await crud_dashboard.sales_summary(db, start=start, end=end)
    items_sold, cogs = await crud_dashboard.sales_items_summary(db, start=start, end=end)
    purchase_amount, purchase_orders = await crud_dashboard.purchase_summary(db, start=start, end=end)

    top_part_rows = await crud_dashboard.top_selling_parts_report(db, start=start, end=end, limit=5)
    top_customer_rows = await crud_dashboard.top_customers(db, start=start, end=end, limit=5)
    top_supplier_rows = await crud_dashboard.top_suppliers(db, start=start, end=end, limit=5)
    category_rows = await crud_dashboard.category_breakdown(db, start=start, end=end, limit=8)
    trend_rows = await crud_dashboard.sales_trend(db, start=start, end=end)
    data_start, data_end = await crud_dashboard.sales_data_range(db)

    gross_profit = money(sales_amount - cogs)
    gross_margin = money(gross_profit / sales_amount * Decimal("100")) if sales_amount else Decimal("0.00")
    avg_order_amount = money(sales_amount / sales_orders) if sales_orders else Decimal("0.00")

    granularity = "month" if _is_month_range(start_date, end_date) else "day"
    if granularity == "month":
        monthly: dict[str, tuple[Decimal, int]] = {}
        for period, amount, count in trend_rows:
            key = period[:7]
            old_amount, old_count = monthly.get(key, (Decimal("0.00"), 0))
            monthly[key] = (old_amount + amount, old_count + count)
        trend = [
            TrendPointOut(
                period=period,
                sales_amount=money(amount),
                order_count=count,
            )
            for period, (amount, count) in monthly.items()
        ]
    else:
        trend = [
            TrendPointOut(
                period=period,
                sales_amount=money(amount),
                order_count=count,
            )
            for period, amount, count in trend_rows
        ]

    return DashboardReportOut(
        start_date=start_date,
        end_date=end_date,
        data_start_date=to_local_date(data_start) if data_start else None,
        data_end_date=to_local_date(data_end) if data_end else None,
        sales_amount=money(sales_amount),
        sales_order_count=sales_orders,
        items_sold=items_sold,
        avg_order_amount=avg_order_amount,
        purchase_amount=money(purchase_amount),
        purchase_order_count=purchase_orders,
        gross_profit=gross_profit,
        gross_margin=gross_margin,
        top_parts=[
            ReportPartOut(
                part_id=part_id,
                part_name=part_name,
                quantity=quantity,
                amount=money(amount),
            )
            for part_id, part_name, quantity, amount in top_part_rows
        ],
        top_customers=[
            TopCustomerOut(
                customer_id=customer_id,
                customer_name=customer_name,
                amount=money(amount),
                order_count=order_count,
            )
            for customer_id, customer_name, amount, order_count in top_customer_rows
        ],
        top_suppliers=[
            TopSupplierOut(
                supplier_id=supplier_id,
                supplier_name=supplier_name,
                amount=money(amount),
                order_count=order_count,
            )
            for supplier_id, supplier_name, amount, order_count in top_supplier_rows
        ],
        category_breakdown=[
            CategorySalesOut(
                category=category,
                quantity=quantity,
                amount=money(amount),
            )
            for category, quantity, amount in category_rows
        ],
        trend=trend,
        trend_granularity=granularity,
        generated_at=datetime.now(UTC),
    )
