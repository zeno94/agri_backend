"""库存流水数据访问。"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_log import InventoryLog


async def list_logs(
    db: AsyncSession,
    *,
    page: int,
    size: int,
    part_id: int | None = None,
    change_type: str | None = None,
) -> tuple[list[InventoryLog], int]:
    conditions = []
    if part_id is not None:
        conditions.append(InventoryLog.part_id == part_id)
    if change_type is not None:
        conditions.append(InventoryLog.change_type == change_type)

    total = await db.scalar(select(func.count(InventoryLog.id)).where(*conditions)) or 0
    rows = await db.scalars(
        select(InventoryLog)
        .where(*conditions)
        .order_by(InventoryLog.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    return list(rows.all()), total
