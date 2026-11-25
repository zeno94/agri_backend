"""客户数据访问。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.customer import Customer, CustomerFollowup
from app.models.enums import OrderStatus
from app.models.sale import SaleOrder


def _stats_subquery():
    return (
        select(
            SaleOrder.customer_id.label("customer_id"),
            func.count(SaleOrder.id).label("order_count"),
            func.coalesce(func.sum(SaleOrder.total_amount), 0).label("total_amount"),
            func.min(SaleOrder.created_at).label("first_order_at"),
            func.max(SaleOrder.created_at).label("last_order_at"),
        )
        .where(SaleOrder.status == OrderStatus.COMPLETED.value)
        .group_by(SaleOrder.customer_id)
        .subquery()
    )


async def get_by_id(db: AsyncSession, customer_id: int) -> Customer | None:
    return await db.get(Customer, customer_id)


async def list_customers(
    db: AsyncSession,
    *,
    page: int,
    size: int,
    keyword: str | None = None,
    town: str | None = None,
    customer_type: str | None = None,
) -> tuple[list[tuple[Customer, int, Decimal, datetime | None, datetime | None]], int]:
    stats = _stats_subquery()
    conditions = [Customer.is_active.is_(True)]
    if keyword:
        escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append(
            or_(
                Customer.name.like(f"%{escaped}%", escape="\\"),
                Customer.phone.like(f"%{escaped}%", escape="\\"),
            )
        )
    if town:
        conditions.append(Customer.town == town)
    if customer_type:
        conditions.append(Customer.customer_type == customer_type)

    total = await db.scalar(select(func.count(Customer.id)).where(*conditions)) or 0
    stmt = (
        select(
            Customer,
            func.coalesce(stats.c.order_count, 0).label("order_count"),
            func.coalesce(stats.c.total_amount, 0).label("total_amount"),
            stats.c.first_order_at,
            stats.c.last_order_at,
        )
        .outerjoin(stats, stats.c.customer_id == Customer.id)
        .where(*conditions)
        .order_by(
            stats.c.last_order_at.is_(None),
            stats.c.last_order_at.desc(),
            Customer.id.asc(),
        )
        .offset((page - 1) * size)
        .limit(size)
    )
    rows = (await db.execute(stmt)).all()
    return [
        (
            row[0],
            int(row[1] or 0),
            Decimal(str(row[2] or 0)),
            row[3],
            row[4],
        )
        for row in rows
    ], int(total)


async def options(db: AsyncSession, limit: int = 2000) -> list[Customer]:
    rows = await db.scalars(
        select(Customer).where(Customer.is_active.is_(True)).order_by(Customer.id.asc()).limit(limit)
    )
    return list(rows.all())


async def create_customer(db: AsyncSession, values: dict[str, Any]) -> Customer:
    customer = Customer(**values)
    db.add(customer)
    await db.flush()
    return customer


async def update_customer(db: AsyncSession, customer: Customer, values: dict[str, Any]) -> Customer:
    for key, value in values.items():
        setattr(customer, key, value)
    await db.flush()
    return customer


async def recent_orders(db: AsyncSession, customer_id: int, limit: int = 10) -> list[SaleOrder]:
    rows = await db.scalars(
        select(SaleOrder)
        .where(SaleOrder.customer_id == customer_id)
        .order_by(SaleOrder.created_at.desc(), SaleOrder.id.desc())
        .limit(limit)
    )
    return list(rows.all())


async def stats_for_customer(db: AsyncSession, customer_id: int):
    stmt = select(
        func.count(SaleOrder.id),
        func.coalesce(func.sum(SaleOrder.total_amount), 0),
        func.min(SaleOrder.created_at),
        func.max(SaleOrder.created_at),
    ).where(
        SaleOrder.customer_id == customer_id,
        SaleOrder.status == OrderStatus.COMPLETED.value,
    )
    return (await db.execute(stmt)).one()


async def list_followups(db: AsyncSession, customer_id: int, limit: int = 20) -> list[CustomerFollowup]:
    rows = await db.scalars(
        select(CustomerFollowup)
        .where(CustomerFollowup.customer_id == customer_id)
        .options(selectinload(CustomerFollowup.operator))
        .order_by(CustomerFollowup.created_at.desc(), CustomerFollowup.id.desc())
        .limit(limit)
    )
    return list(rows.all())


async def create_followup(db: AsyncSession, values: dict[str, Any]) -> CustomerFollowup:
    followup = CustomerFollowup(**values)
    db.add(followup)
    await db.flush()
    return followup


async def get_followup(db: AsyncSession, followup_id: int) -> CustomerFollowup | None:
    return await db.scalar(
        select(CustomerFollowup)
        .where(CustomerFollowup.id == followup_id)
        .options(selectinload(CustomerFollowup.operator))
    )
