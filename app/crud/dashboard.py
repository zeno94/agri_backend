"""看板统计查询：全部在数据库侧聚合（func.sum / group_by），避免把明细拉到应用层。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.customer import Customer
from app.models.enums import OrderStatus
from app.models.part import Part
from app.models.purchase import PurchaseOrder
from app.models.sale import SaleItem, SaleOrder
from app.models.supplier import Supplier


def _completed_sale_conditions(start: datetime, end: datetime) -> list:
    return [
        SaleOrder.status == OrderStatus.COMPLETED.value,
        SaleOrder.created_at >= start,
        SaleOrder.created_at < end,
    ]


def _completed_purchase_conditions(start: datetime, end: datetime) -> list:
    return [
        PurchaseOrder.status == OrderStatus.COMPLETED.value,
        PurchaseOrder.created_at >= start,
        PurchaseOrder.created_at < end,
    ]


def _local_date_expr(db: AsyncSession, at: datetime):
    """返回按业务时区截断到“日”的 SQL 表达式。

    MySQL 与 SQLite 的日期函数不同：MySQL 用 CONVERT_TZ + DATE，
    SQLite 用 DATE(..., '+480 minutes')。默认业务时区为 Asia/Shanghai，
    没有夏令时；如改成有 DST 的时区，区间跨 DST 时边界会有小时级偏差。
    """
    aware = at.replace(tzinfo=UTC) if at.tzinfo is None else at
    offset = aware.astimezone(settings.tzinfo).utcoffset() or timedelta(0)
    total_minutes = int(offset.total_seconds() // 60)

    dialect = db.get_bind().dialect.name
    if dialect == "mysql":
        sign = "+" if total_minutes >= 0 else "-"
        hours, minutes = divmod(abs(total_minutes), 60)
        offset_text = f"{sign}{hours:02d}:{minutes:02d}"
        return func.date(func.convert_tz(SaleOrder.created_at, "+00:00", offset_text))

    # SQLite（单元测试）以及未知方言：用分钟偏移，兼容 +5:30 这类时区。
    return func.date(SaleOrder.created_at, f"{total_minutes:+d} minutes")


async def sales_summary(db: AsyncSession, *, start: datetime, end: datetime) -> tuple[Decimal, int]:
    """返回指定时间区间内已完成销售单的 (销售额合计, 单据数)。"""
    stmt = select(
        func.coalesce(func.sum(SaleOrder.total_amount), 0),
        func.count(SaleOrder.id),
    ).where(*_completed_sale_conditions(start, end))
    total_amount, order_count = (await db.execute(stmt)).one()
    return Decimal(str(total_amount)), int(order_count)


async def purchase_summary(db: AsyncSession, *, start: datetime, end: datetime) -> tuple[Decimal, int]:
    """返回指定区间内已完成采购单的 (采购额合计, 单据数)。"""
    stmt = select(
        func.coalesce(func.sum(PurchaseOrder.total_amount), 0),
        func.count(PurchaseOrder.id),
    ).where(*_completed_purchase_conditions(start, end))
    total_amount, order_count = (await db.execute(stmt)).one()
    return Decimal(str(total_amount)), int(order_count)


async def sales_items_summary(db: AsyncSession, *, start: datetime, end: datetime) -> tuple[int, Decimal]:
    """返回指定区间销售的 (件数, 按当前参考进货价估算的销售成本)。"""
    stmt = (
        select(
            func.coalesce(func.sum(SaleItem.quantity), 0),
            func.coalesce(func.sum(Part.purchase_price * SaleItem.quantity), 0),
        )
        .select_from(SaleItem)
        .join(SaleOrder, SaleOrder.id == SaleItem.order_id)
        .join(Part, Part.id == SaleItem.part_id)
        .where(*_completed_sale_conditions(start, end))
    )
    quantity, cost = (await db.execute(stmt)).one()
    return int(quantity), Decimal(str(cost))


async def top_selling_parts(
    db: AsyncSession, *, start: datetime, end: datetime, limit: int = 5
) -> list[tuple[int, str, int]]:
    """指定区间内销量 Top N 配件：[(part_id, part_name, quantity), ...]。"""
    total_quantity = func.sum(SaleItem.quantity)
    stmt = (
        select(Part.id, Part.name, total_quantity.label("total_quantity"))
        .join(SaleItem, SaleItem.part_id == Part.id)
        .join(SaleOrder, SaleOrder.id == SaleItem.order_id)
        .where(*_completed_sale_conditions(start, end))
        .group_by(Part.id, Part.name)
        .order_by(total_quantity.desc(), Part.id.asc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return [(int(row[0]), str(row[1]), int(row[2] or 0)) for row in rows]


async def top_selling_parts_report(
    db: AsyncSession, *, start: datetime, end: datetime, limit: int = 5
) -> list[tuple[int, str, int, Decimal]]:
    """按销售额排序的配件 Top N：[(id, name, quantity, amount), ...]。"""
    quantity = func.sum(SaleItem.quantity)
    amount = func.sum(SaleItem.price * SaleItem.quantity)
    stmt = (
        select(Part.id, Part.name, quantity.label("quantity"), amount.label("amount"))
        .join(SaleItem, SaleItem.part_id == Part.id)
        .join(SaleOrder, SaleOrder.id == SaleItem.order_id)
        .where(*_completed_sale_conditions(start, end))
        .group_by(Part.id, Part.name)
        .order_by(amount.desc(), Part.id.asc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return [(int(row[0]), str(row[1]), int(row[2] or 0), Decimal(str(row[3] or 0))) for row in rows]


async def top_customers(
    db: AsyncSession, *, start: datetime, end: datetime, limit: int = 5
) -> list[tuple[int, str, Decimal, int]]:
    """销售额 Top N 客户：[(customer_id, name, amount, order_count), ...]。"""
    amount = func.sum(SaleOrder.total_amount)
    order_count = func.count(SaleOrder.id)
    stmt = (
        select(
            Customer.id,
            Customer.name,
            amount.label("amount"),
            order_count.label("order_count"),
        )
        .select_from(SaleOrder)
        .join(Customer, Customer.id == SaleOrder.customer_id)
        .where(*_completed_sale_conditions(start, end))
        .group_by(Customer.id, Customer.name)
        .order_by(amount.desc(), Customer.id.asc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return [(int(row[0]), str(row[1]), Decimal(str(row[2] or 0)), int(row[3] or 0)) for row in rows]


async def top_suppliers(
    db: AsyncSession, *, start: datetime, end: datetime, limit: int = 5
) -> list[tuple[int, str, Decimal, int]]:
    """采购额 Top N 供应商：[(supplier_id, name, amount, order_count), ...]。"""
    amount = func.sum(PurchaseOrder.total_amount)
    order_count = func.count(PurchaseOrder.id)
    stmt = (
        select(
            Supplier.id,
            Supplier.name,
            amount.label("amount"),
            order_count.label("order_count"),
        )
        .select_from(PurchaseOrder)
        .join(Supplier, Supplier.id == PurchaseOrder.supplier_id)
        .where(*_completed_purchase_conditions(start, end))
        .group_by(Supplier.id, Supplier.name)
        .order_by(amount.desc(), Supplier.id.asc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return [(int(row[0]), str(row[1]), Decimal(str(row[2] or 0)), int(row[3] or 0)) for row in rows]


async def category_breakdown(
    db: AsyncSession, *, start: datetime, end: datetime, limit: int = 10
) -> list[tuple[str, int, Decimal]]:
    """分类销售：[(category, quantity, amount), ...]。"""
    category = func.coalesce(Part.category, "未分类")
    quantity = func.sum(SaleItem.quantity)
    amount = func.sum(SaleItem.price * SaleItem.quantity)
    stmt = (
        select(category.label("category"), quantity.label("quantity"), amount.label("amount"))
        .select_from(SaleItem)
        .join(SaleOrder, SaleOrder.id == SaleItem.order_id)
        .join(Part, Part.id == SaleItem.part_id)
        .where(*_completed_sale_conditions(start, end))
        .group_by(category)
        .order_by(amount.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return [(str(row[0] or "未分类"), int(row[1] or 0), Decimal(str(row[2] or 0))) for row in rows]


async def sales_trend(db: AsyncSession, *, start: datetime, end: datetime) -> list[tuple[str, Decimal, int]]:
    """按业务时区自然日聚合销售趋势：[(YYYY-MM-DD, amount, count), ...]。"""
    period = _local_date_expr(db, end)
    amount = func.sum(SaleOrder.total_amount)
    order_count = func.count(SaleOrder.id)
    stmt = (
        select(period.label("period"), amount.label("amount"), order_count.label("count"))
        .where(*_completed_sale_conditions(start, end))
        .group_by(period)
        .order_by(period)
    )
    rows = (await db.execute(stmt)).all()
    return [(str(row[0])[:10], Decimal(str(row[1] or 0)), int(row[2] or 0)) for row in rows]


async def sales_data_range(db: AsyncSession) -> tuple[datetime | None, datetime | None]:
    """库内已完成销售单的最早 / 最晚创建时间。"""
    stmt = select(func.min(SaleOrder.created_at), func.max(SaleOrder.created_at)).where(
        SaleOrder.status == OrderStatus.COMPLETED.value
    )
    first, last = (await db.execute(stmt)).one()
    return first, last
