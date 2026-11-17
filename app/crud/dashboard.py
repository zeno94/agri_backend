"""看板统计查询：全部在数据库侧聚合（func.sum / group_by），避免把明细拉到应用层。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import OrderStatus
from app.models.part import Part
from app.models.sale import SaleItem, SaleOrder


async def sales_summary(db: AsyncSession, *, start: datetime, end: datetime) -> tuple[Decimal, int]:
    """返回指定时间区间内已完成销售单的 (销售额合计, 单据数)。"""
    stmt = select(
        func.coalesce(func.sum(SaleOrder.total_amount), 0),
        func.count(SaleOrder.id),
    ).where(
        SaleOrder.status == OrderStatus.COMPLETED.value,
        SaleOrder.created_at >= start,
        SaleOrder.created_at < end,
    )
    total_amount, order_count = (await db.execute(stmt)).one()
    return Decimal(str(total_amount)), int(order_count)


async def top_selling_parts(
    db: AsyncSession, *, start: datetime, end: datetime, limit: int = 5
) -> list[tuple[int, str, int]]:
    """指定区间内销量 Top N 配件：[(part_id, part_name, quantity), ...]。"""
    total_quantity = func.sum(SaleItem.quantity)
    stmt = (
        select(Part.id, Part.name, total_quantity.label("total_quantity"))
        .join(SaleItem, SaleItem.part_id == Part.id)
        .join(SaleOrder, SaleOrder.id == SaleItem.order_id)
        .where(
            SaleOrder.status == OrderStatus.COMPLETED.value,
            SaleOrder.created_at >= start,
            SaleOrder.created_at < end,
        )
        .group_by(Part.id, Part.name)
        .order_by(total_quantity.desc(), Part.id.asc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return [(int(row[0]), str(row[1]), int(row[2] or 0)) for row in rows]
