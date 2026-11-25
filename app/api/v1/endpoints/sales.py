"""销售出库接口。"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.api.deps import CacheClient, CurrentUser, DbSession, require_module
from app.core import idempotency, metrics
from app.core.exceptions import AppError
from app.schemas.sale import SaleOrderCreate, SaleOrderOut, SaleOrderPage
from app.services import audit as audit_service
from app.services import sale as sale_service

router = APIRouter(prefix="/sales", tags=["销售出库"])

IDEMPOTENCY_SCOPE = "sales.outbound"
CREATED = status.HTTP_201_CREATED


@router.post(
    "/outbound",
    response_model=SaleOrderOut,
    status_code=CREATED,
    summary="销售出库（悲观锁防超卖 + 幂等）",
    dependencies=[Depends(require_module("sale"))],
    description=(
        "按 part_id 升序 SELECT ... FOR UPDATE 锁定配件行，全部校验通过后才扣减库存；"
        "任意明细库存不足返回 409 并整单回滚，不产生销售单与库存流水。\n\n"
        "幂等：请求头可带 `Idempotency-Key`（8~64 位字母数字下划线短横线）。"
        "同一个 key 重复提交只执行一次，后续请求回放首次结果并返回 `Idempotent-Replay: true`；"
        "首次请求仍在处理时返回 409 `REQUEST_IN_PROGRESS`。"
    ),
)
async def create_outbound(
    payload: SaleOrderCreate,
    request: Request,
    db: DbSession,
    cache: CacheClient,
    current_user: CurrentUser,
) -> SaleOrderOut | JSONResponse:
    idem_key = request.headers.get("Idempotency-Key")

    # 命中幂等键：直接回放首次结果，不重复扣库存，也不重复写审计
    replay = await idempotency.acquire(cache, IDEMPOTENCY_SCOPE, idem_key)
    if replay is not None:
        metrics.record_event("idempotent.replay")
        return idempotency.replay_response(replay)

    try:
        result = await sale_service.create_outbound(db, cache, payload, current_user)
    except AppError as exc:
        # 执行失败要释放键，否则客户端用同一个 key 重试会一直拿到上次的错误
        await idempotency.release(cache, IDEMPOTENCY_SCOPE, idem_key)
        # service 层异常时会 rollback，ORM 对象被 expire；先 refresh 再取快照
        await db.refresh(current_user)
        await audit_service.record(
            db,
            user=current_user,
            action="sale.outbound",
            module="sales",
            status_code=exc.status_code,
            success=False,
            error_code=exc.code,
            method="POST",
            path=request.url.path,
            detail={
                "request": payload.model_dump(),
                "message": exc.message,
                "error_detail": exc.detail,
            },
            request=request,
        )
        raise
    except Exception:
        await idempotency.release(cache, IDEMPOTENCY_SCOPE, idem_key)
        raise

    await audit_service.record(
        db,
        user=current_user,
        action="sale.outbound",
        module="sales",
        resource_type="sale_order",
        resource_id=result.id,
        method="POST",
        path=request.url.path,
        detail={
            "order_no": result.order_no,
            "customer_id": result.customer_id,
            "total_amount": result.total_amount,
            "items": [
                {
                    "part_id": item.part_id,
                    "quantity": item.quantity,
                    "price": item.price,
                    "amount": item.amount,
                }
                for item in result.items
            ],
        },
        request=request,
    )
    await idempotency.store(cache, IDEMPOTENCY_SCOPE, idem_key, CREATED, jsonable_encoder(result))
    metrics.record_event("sale.outbound")
    return result


@router.get(
    "",
    response_model=SaleOrderPage,
    summary="销售单分页查询",
    dependencies=[Depends(require_module("sales"))],
)
async def list_sales(
    db: DbSession,
    _current_user: CurrentUser,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    start_date: Annotated[date | None, Query(description="开始日期（含，Asia/Shanghai）")] = None,
    end_date: Annotated[date | None, Query(description="结束日期（含，Asia/Shanghai）")] = None,
    customer_id: Annotated[int | None, Query(gt=0, description="客户 ID")] = None,
    keyword: Annotated[str | None, Query(max_length=32, description="销售单号关键词")] = None,
) -> SaleOrderPage:
    return await sale_service.list_outbound_orders(
        db,
        page=page,
        size=size,
        start_date=start_date,
        end_date=end_date,
        customer_id=customer_id,
        keyword=keyword.strip() if keyword else None,
    )
