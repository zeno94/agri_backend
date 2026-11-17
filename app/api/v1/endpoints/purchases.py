"""采购入库接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CacheClient, CurrentUser, DbSession
from app.schemas.common import Page
from app.schemas.purchase import PurchaseOrderCreate, PurchaseOrderOut
from app.services import purchase as purchase_service

router = APIRouter(prefix="/purchases", tags=["采购入库"])


@router.post(
    "/inbound",
    response_model=PurchaseOrderOut,
    status_code=status.HTTP_201_CREATED,
    summary="采购入库",
    description=(
        "在同一数据库事务中：锁定配件行 → 增加库存 → 写采购明细 → 写库存流水 → "
        "生成 completed 状态的采购单。任一步失败整单回滚。"
    ),
)
async def create_inbound(
    payload: PurchaseOrderCreate,
    db: DbSession,
    cache: CacheClient,
    current_user: CurrentUser,
) -> PurchaseOrderOut:
    return await purchase_service.create_inbound(db, cache, payload, current_user)


@router.get("", response_model=Page[PurchaseOrderOut], summary="采购单分页查询")
async def list_purchases(
    db: DbSession,
    _current_user: CurrentUser,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[PurchaseOrderOut]:
    return await purchase_service.list_inbound_orders(db, page=page, size=size)
