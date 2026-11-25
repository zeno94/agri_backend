"""采购单 / 销售单数据访问。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.purchase import PurchaseOrder
from app.models.sale import SaleOrder


async def get_purchase_detail(db: AsyncSession, order_id: int) -> PurchaseOrder | None:
    stmt = select(PurchaseOrder).where(PurchaseOrder.id == order_id).options(selectinload(PurchaseOrder.items))
    return await db.scalar(stmt)


async def get_sale_detail(db: AsyncSession, order_id: int) -> SaleOrder | None:
    stmt = select(SaleOrder).where(SaleOrder.id == order_id).options(selectinload(SaleOrder.items))
    return await db.scalar(stmt)


async def list_purchase_orders(db: AsyncSession, *, page: int, size: int) -> tuple[list[PurchaseOrder], int]:
    total = await db.scalar(select(func.count(PurchaseOrder.id))) or 0
    rows = await db.scalars(
        select(PurchaseOrder)
        .options(selectinload(PurchaseOrder.items))
        .order_by(PurchaseOrder.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    return list(rows.all()), total


async def list_sale_orders(
    db: AsyncSession,
    *,
    page: int,
    size: int,
    start: datetime | None = None,
    end: datetime | None = None,
    customer_id: int | None = None,
    keyword: str | None = None,
) -> tuple[list[SaleOrder], int, Decimal]:
    """销售单分页查询，返回 (当前页, 总单数, 筛选结果总金额)。"""
    conditions = []
    if start is not None:
        conditions.append(SaleOrder.created_at >= start)
    if end is not None:
        conditions.append(SaleOrder.created_at < end)
    if customer_id is not None:
        conditions.append(SaleOrder.customer_id == customer_id)
    if keyword:
        escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append(SaleOrder.order_no.like(f"%{escaped}%", escape="\\"))

    summary = await db.execute(
        select(
            func.count(SaleOrder.id),
            func.coalesce(func.sum(SaleOrder.total_amount), 0),
        ).where(*conditions)
    )
    total, total_amount = summary.one()

    rows = await db.scalars(
        select(SaleOrder)
        .where(*conditions)
        .options(selectinload(SaleOrder.items))
        .order_by(SaleOrder.created_at.desc(), SaleOrder.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    return list(rows.all()), int(total), Decimal(str(total_amount))
