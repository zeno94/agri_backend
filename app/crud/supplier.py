"""供应商数据访问。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import OrderStatus
from app.models.purchase import PurchaseOrder
from app.models.supplier import Supplier


def _stats_subquery():
    return (
        select(
            PurchaseOrder.supplier_id.label("supplier_id"),
            func.count(PurchaseOrder.id).label("order_count"),
            func.coalesce(func.sum(PurchaseOrder.total_amount), 0).label("total_amount"),
            func.max(PurchaseOrder.created_at).label("last_order_at"),
        )
        .where(PurchaseOrder.status == OrderStatus.COMPLETED.value)
        .group_by(PurchaseOrder.supplier_id)
        .subquery()
    )


async def get_by_id(db: AsyncSession, supplier_id: int) -> Supplier | None:
    return await db.get(Supplier, supplier_id)


async def list_suppliers(
    db: AsyncSession,
    *,
    page: int,
    size: int,
    keyword: str | None = None,
) -> tuple[list[tuple[Supplier, int, Decimal, datetime | None]], int]:
    stats = _stats_subquery()
    conditions = []
    if keyword:
        escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append(
            or_(
                Supplier.name.like(f"%{escaped}%", escape="\\"),
                Supplier.phone.like(f"%{escaped}%", escape="\\"),
                Supplier.contact_person.like(f"%{escaped}%", escape="\\"),
            )
        )

    total = await db.scalar(select(func.count(Supplier.id)).where(*conditions)) or 0
    stmt = (
        select(
            Supplier,
            func.coalesce(stats.c.order_count, 0).label("order_count"),
            func.coalesce(stats.c.total_amount, 0).label("total_amount"),
            stats.c.last_order_at,
        )
        .outerjoin(stats, stats.c.supplier_id == Supplier.id)
        .where(*conditions)
        .order_by(Supplier.id.asc())
        .offset((page - 1) * size)
        .limit(size)
    )
    rows = (await db.execute(stmt)).all()
    return [(row[0], int(row[1] or 0), Decimal(str(row[2] or 0)), row[3]) for row in rows], int(total)


async def options(db: AsyncSession, limit: int = 1000) -> list[Supplier]:
    rows = await db.scalars(
        select(Supplier).where(Supplier.is_active.is_(True)).order_by(Supplier.id.asc()).limit(limit)
    )
    return list(rows.all())


async def create_supplier(db: AsyncSession, values: dict[str, Any]) -> Supplier:
    supplier = Supplier(**values)
    db.add(supplier)
    await db.flush()
    return supplier


async def update_supplier(db: AsyncSession, supplier: Supplier, values: dict[str, Any]) -> Supplier:
    for key, value in values.items():
        setattr(supplier, key, value)
    await db.flush()
    return supplier
