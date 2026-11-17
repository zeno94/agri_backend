"""库存流水查询服务。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import inventory as crud_inventory
from app.models.enums import ChangeType
from app.schemas.common import Page
from app.schemas.inventory import InventoryLogOut
from app.services.common import calc_pages


async def list_logs(
    db: AsyncSession,
    *,
    page: int,
    size: int,
    part_id: int | None = None,
    change_type: ChangeType | None = None,
) -> Page[InventoryLogOut]:
    rows, total = await crud_inventory.list_logs(
        db,
        page=page,
        size=size,
        part_id=part_id,
        change_type=change_type.value if change_type else None,
    )
    items = [
        InventoryLogOut(
            id=log.id,
            part_id=log.part_id,
            part_name=log.part.name if log.part is not None else "",
            change_type=ChangeType(log.change_type),
            change_qty=log.change_qty,
            before_stock=log.before_stock,
            after_stock=log.after_stock,
            operator_id=log.operator_id,
            operator_name=log.operator.username if log.operator is not None else "",
            remark=log.remark,
            created_at=log.created_at,
        )
        for log in rows
    ]
    return Page[InventoryLogOut](
        items=items,
        total=total,
        page=page,
        size=size,
        pages=calc_pages(total, size),
    )
