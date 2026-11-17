"""往来单位数据访问。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.partner import Partner


async def get_by_id(db: AsyncSession, partner_id: int) -> Partner | None:
    return await db.get(Partner, partner_id)


async def list_partners(
    db: AsyncSession,
    *,
    page: int,
    size: int,
    partner_type: str | None = None,
    name: str | None = None,
) -> tuple[list[Partner], int]:
    conditions = []
    if partner_type:
        conditions.append(Partner.type == partner_type)
    if name:
        keyword = name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append(Partner.name.like(f"%{keyword}%", escape="\\"))

    total = await db.scalar(select(func.count(Partner.id)).where(*conditions)) or 0
    rows = await db.scalars(
        select(Partner).where(*conditions).order_by(Partner.id.desc()).offset((page - 1) * size).limit(size)
    )
    return list(rows.all()), total


async def create_partner(db: AsyncSession, values: dict[str, Any]) -> Partner:
    partner = Partner(**values)
    db.add(partner)
    await db.flush()
    return partner
