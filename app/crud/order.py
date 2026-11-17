"""采购单 / 销售单数据访问。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.purchase import PurchaseOrder
from app.models.sale import SaleOrder


async def get_purchase_detail(db: AsyncSession, order_id: int) -> PurchaseOrder | None:
    stmt = (
        select(PurchaseOrder)
        .where(PurchaseOrder.id == order_id)
        .options(selectinload(PurchaseOrder.items))
    )
    return await db.scalar(stmt)


async def get_sale_detail(db: AsyncSession, order_id: int) -> SaleOrder | None:
    stmt = (
        select(SaleOrder)
        .where(SaleOrder.id == order_id)
        .options(selectinload(SaleOrder.items))
    )
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


async def list_sale_orders(db: AsyncSession, *, page: int, size: int) -> tuple[list[SaleOrder], int]:
    total = await db.scalar(select(func.count(SaleOrder.id))) or 0
    rows = await db.scalars(
        select(SaleOrder)
        .options(selectinload(SaleOrder.items))
        .order_by(SaleOrder.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    return list(rows.all()), total
