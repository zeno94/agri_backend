"""配件数据访问。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.part import Part


def _escape_like(keyword: str) -> str:
    """转义 LIKE 通配符，防止用户输入 % / _ 导致全表匹配。"""
    escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _filtered_query(name: str | None, category: str | None) -> Select[tuple[Part]]:
    stmt = select(Part)
    if name:
        stmt = stmt.where(Part.name.like(_escape_like(name), escape="\\"))
    if category:
        stmt = stmt.where(Part.category == category)
    return stmt


async def get_by_id(db: AsyncSession, part_id: int) -> Part | None:
    return await db.get(Part, part_id)


async def list_parts(
    db: AsyncSession,
    *,
    page: int,
    size: int,
    name: str | None = None,
    category: str | None = None,
) -> tuple[list[Part], int]:
    stmt = _filtered_query(name, category)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await db.scalars(stmt.order_by(Part.id.desc()).offset((page - 1) * size).limit(size))
    return list(rows.all()), total


async def list_warning_parts(db: AsyncSession) -> list[Part]:
    """库存小于等于安全库存的配件，缺货最严重的排在最前。"""
    stmt = (
        select(Part)
        .where(Part.stock <= Part.safe_stock)
        .order_by((Part.stock - Part.safe_stock).asc(), Part.id.asc())
    )
    rows = await db.scalars(stmt)
    return list(rows.all())


async def lock_parts_by_ids(db: AsyncSession, part_ids: Sequence[int]) -> dict[int, Part]:
    """按主键升序加行锁（SELECT ... FOR UPDATE），固定加锁顺序以降低死锁概率。

    注意：调用方必须处于事务中，锁会在事务提交/回滚后释放。
    """
    ordered_ids = sorted(set(part_ids))
    if not ordered_ids:
        return {}
    stmt = select(Part).where(Part.id.in_(ordered_ids)).order_by(Part.id).with_for_update()
    rows = await db.scalars(stmt)
    return {part.id: part for part in rows.all()}


async def create_part(db: AsyncSession, values: dict[str, Any]) -> Part:
    part = Part(**values)
    db.add(part)
    await db.flush()
    return part


async def apply_update(db: AsyncSession, part: Part, values: dict[str, Any]) -> Part:
    for field, value in values.items():
        setattr(part, field, value)
    await db.flush()
    return part
