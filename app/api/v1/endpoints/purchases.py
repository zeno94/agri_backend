"""采购入库接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.api.deps import CacheClient, CurrentUser, DbSession, require_module
from app.core import idempotency, metrics
from app.core.exceptions import AppError
from app.schemas.common import Page
from app.schemas.purchase import PurchaseOrderCreate, PurchaseOrderOut
from app.services import audit as audit_service
from app.services import purchase as purchase_service

router = APIRouter(prefix="/purchases", tags=["采购入库"], dependencies=[Depends(require_module("purchase"))])

IDEMPOTENCY_SCOPE = "purchases.inbound"
CREATED = status.HTTP_201_CREATED


@router.post(
    "/inbound",
    response_model=PurchaseOrderOut,
    status_code=CREATED,
    summary="采购入库（幂等）",
    description=(
        "在同一数据库事务中：锁定配件行 → 增加库存 → 写采购明细 → 写库存流水 → "
        "生成 completed 状态的采购单。任一步失败整单回滚。\n\n"
        "幂等：请求头可带 `Idempotency-Key`，同一个 key 重复提交只执行一次。"
    ),
)
async def create_inbound(
    payload: PurchaseOrderCreate,
    request: Request,
    db: DbSession,
    cache: CacheClient,
    current_user: CurrentUser,
) -> PurchaseOrderOut | JSONResponse:
    idem_key = request.headers.get("Idempotency-Key")

    replay = await idempotency.acquire(cache, IDEMPOTENCY_SCOPE, idem_key)
    if replay is not None:
        metrics.record_event("idempotent.replay")
        return idempotency.replay_response(replay)

    try:
        result = await purchase_service.create_inbound(db, cache, payload, current_user)
    except AppError as exc:
        await idempotency.release(cache, IDEMPOTENCY_SCOPE, idem_key)
        # service 层异常时会 rollback，ORM 对象被 expire；先 refresh 再取快照
        await db.refresh(current_user)
        await audit_service.record(
            db,
            user=current_user,
            action="purchase.inbound",
            module="purchases",
            status_code=exc.status_code,
            success=False,
            error_code=exc.code,
            method="POST",
            path=request.url.path,
            detail={"request": payload.model_dump(), "message": exc.message},
            request=request,
        )
        raise
    except Exception:
        await idempotency.release(cache, IDEMPOTENCY_SCOPE, idem_key)
        raise

    await audit_service.record(
        db,
        user=current_user,
        action="purchase.inbound",
        module="purchases",
        resource_type="purchase_order",
        resource_id=result.id,
        method="POST",
        path=request.url.path,
        detail={
            "order_no": result.order_no,
            "supplier_id": result.supplier_id,
            "total_amount": result.total_amount,
            "item_count": len(result.items),
        },
        request=request,
    )
    await idempotency.store(cache, IDEMPOTENCY_SCOPE, idem_key, CREATED, jsonable_encoder(result))
    metrics.record_event("purchase.inbound")
    return result


@router.get("", response_model=Page[PurchaseOrderOut], summary="采购单分页查询")
async def list_purchases(
    db: DbSession,
    _current_user: CurrentUser,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[PurchaseOrderOut]:
    return await purchase_service.list_inbound_orders(db, page=page, size=size)
