"""库存流水查询接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, DbSession, require_module
from app.models.enums import ChangeType
from app.schemas.common import Page
from app.schemas.inventory import InventoryLogOut
from app.services import inventory as inventory_service

router = APIRouter(prefix="/inventory", tags=["库存流水"], dependencies=[Depends(require_module("warning"))])


@router.get("/logs", response_model=Page[InventoryLogOut], summary="库存变动流水分页查询")
async def list_inventory_logs(
    db: DbSession,
    _current_user: CurrentUser,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    part_id: Annotated[int | None, Query(gt=0, description="按配件筛选")] = None,
    change_type: Annotated[ChangeType | None, Query(description="in / out / check")] = None,
) -> Page[InventoryLogOut]:
    return await inventory_service.list_logs(
        db,
        page=page,
        size=size,
        part_id=part_id,
        change_type=change_type,
    )
