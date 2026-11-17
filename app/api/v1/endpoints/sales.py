"""销售出库接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CacheClient, CurrentUser, DbSession
from app.schemas.common import Page
from app.schemas.sale import SaleOrderCreate, SaleOrderOut
from app.services import sale as sale_service

router = APIRouter(prefix="/sales", tags=["销售出库"])


@router.post(
    "/outbound",
    response_model=SaleOrderOut,
    status_code=status.HTTP_201_CREATED,
    summary="销售出库（悲观锁防超卖）",
    description=(
        "按 part_id 升序 SELECT ... FOR UPDATE 锁定配件行，全部校验通过后才扣减库存；"
        "任意明细库存不足返回 409 并整单回滚，不产生销售单与库存流水。"
    ),
)
async def create_outbound(
    payload: SaleOrderCreate,
    db: DbSession,
    cache: CacheClient,
    current_user: CurrentUser,
) -> SaleOrderOut:
    return await sale_service.create_outbound(db, cache, payload, current_user)


@router.get("", response_model=Page[SaleOrderOut], summary="销售单分页查询")
async def list_sales(
    db: DbSession,
    _current_user: CurrentUser,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[SaleOrderOut]:
    return await sale_service.list_outbound_orders(db, page=page, size=size)
