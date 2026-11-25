"""销售出库服务（防超卖核心）。

并发安全设计：
- 在同一个事务内，按 part_id 升序对每个配件执行 SELECT ... FOR UPDATE（悲观行锁）；
- 先「全部校验」再「统一扣减」：只要有一条库存不足，整单回滚，绝不出现部分扣减；
- 锁定顺序固定，避免多单互相持锁导致死锁；
- 校验-扣减在锁内完成，杜绝「查询时够、扣减时不够」的超卖窗口。

对于 MySQL InnoDB，`SELECT ... FOR UPDATE` 会阻塞其他事务对同一行的加锁读/更新，
直到当前事务 commit 或 rollback 释放锁。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import invalidate_parts_cache
from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.core.money import generate_order_no, money
from app.core.time import local_day_end_exclusive, local_day_start
from app.crud import customer as crud_customer
from app.crud import order as crud_order
from app.crud import part as crud_part
from app.models.enums import ChangeType, OrderStatus, UserRole
from app.models.inventory_log import InventoryLog
from app.models.sale import SaleItem, SaleOrder
from app.models.user import User
from app.schemas.order import OrderItemOut
from app.schemas.sale import SaleOrderCreate, SaleOrderOut, SaleOrderPage
from app.services.common import calc_pages
from app.services.customer import customer_display_name as build_customer_display_name

logger = get_logger(__name__)


def _to_out(order: SaleOrder) -> SaleOrderOut:
    return SaleOrderOut(
        id=order.id,
        order_no=order.order_no,
        customer_id=order.customer_id,
        customer_name=order.customer.name if order.customer is not None else "",
        customer_display_name=(build_customer_display_name(order.customer) if order.customer is not None else ""),
        total_amount=money(order.total_amount),
        status=OrderStatus(order.status),
        operator_id=order.operator_id,
        operator_name=order.operator.username if order.operator is not None else "",
        remark=order.remark,
        created_at=order.created_at,
        items=[
            OrderItemOut(
                part_id=item.part_id,
                part_name=item.part.name if item.part is not None else "",
                quantity=item.quantity,
                price=item.price,
                amount=money(item.price * item.quantity),
            )
            for item in order.items
        ],
    )


async def create_outbound(
    db: AsyncSession,
    redis: Redis | None,
    payload: SaleOrderCreate,
    operator: User,
) -> SaleOrderOut:
    customer = await crud_customer.get_by_id(db, payload.customer_id)
    if customer is None or not customer.is_active:
        raise AppError("CUSTOMER_NOT_FOUND", "客户不存在或已停用", 404)

    # 成交价权限：员工按建议零售价成交，只有 boss 可以手动改价
    if operator.role != UserRole.BOSS.value:
        overridden = [item.part_id for item in payload.items if item.price is not None]
        if overridden:
            raise AppError(
                "PRICE_OVERRIDE_FORBIDDEN",
                "仅管理员可以调整销售成交价，员工请按建议零售价成交",
                403,
                detail={"part_ids": overridden},
            )

    order_id: int | None = None
    try:
        # 1) 悲观锁：统一按 part_id 升序锁定，降低死锁概率
        parts = await crud_part.lock_parts_by_ids(db, [item.part_id for item in payload.items])

        missing = sorted({item.part_id for item in payload.items} - parts.keys())
        if missing:
            raise AppError("PART_NOT_FOUND", "部分配件不存在", 404, detail={"part_ids": missing})

        # 2) 先完成全部库存校验，任何一条不足立即抛错并回滚
        shortages = [
            {
                "part_id": item.part_id,
                "part_name": parts[item.part_id].name,
                "requested": item.quantity,
                "available": parts[item.part_id].stock,
            }
            for item in payload.items
            if parts[item.part_id].stock < item.quantity
        ]
        if shortages:
            logger.warning("销售出库库存不足，整单回滚：operator=%s customer=%s", operator.id, customer.id)
            raise AppError(
                "INSUFFICIENT_STOCK",
                "库存不足，销售单已回滚",
                409,
                detail={"items": shortages},
            )

        # 3) 校验通过后创建单据并统一扣减库存
        order = SaleOrder(
            order_no=generate_order_no("SO"),
            customer_id=customer.id,
            operator_id=operator.id,
            total_amount=Decimal("0.00"),
            status=OrderStatus.COMPLETED.value,
            remark=payload.remark,
        )
        db.add(order)
        await db.flush()

        total_amount = Decimal("0.00")
        for item in payload.items:
            part = parts[item.part_id]
            unit_price = money(item.price if item.price is not None else part.sale_price)
            before_stock = part.stock
            part.stock = before_stock - item.quantity

            db.add(
                SaleItem(
                    order_id=order.id,
                    part_id=part.id,
                    quantity=item.quantity,
                    price=unit_price,
                )
            )
            db.add(
                InventoryLog(
                    part_id=part.id,
                    change_type=ChangeType.OUT.value,
                    change_qty=-item.quantity,
                    before_stock=before_stock,
                    after_stock=part.stock,
                    operator_id=operator.id,
                    remark=f"销售出库 {order.order_no}",
                )
            )
            total_amount += unit_price * item.quantity

        order.total_amount = money(total_amount)
        await db.commit()
        order_id = order.id
    except Exception:
        # 库存不足 / 任何异常：释放行锁，单据、明细、流水都不会落库
        await db.rollback()
        raise

    await invalidate_parts_cache(redis)

    detail = await crud_order.get_sale_detail(db, order_id)
    if detail is None:  # pragma: no cover - 正常流程不可能出现
        raise AppError("ORDER_NOT_FOUND", "销售单创建后查询失败", 500)
    return _to_out(detail)


async def list_outbound_orders(
    db: AsyncSession,
    *,
    page: int,
    size: int,
    start_date: date | None = None,
    end_date: date | None = None,
    customer_id: int | None = None,
    keyword: str | None = None,
) -> SaleOrderPage:
    if start_date and end_date and start_date > end_date:
        raise AppError("INVALID_DATE_RANGE", "开始日期不能晚于结束日期", 400)

    rows, total, total_amount = await crud_order.list_sale_orders(
        db,
        page=page,
        size=size,
        start=local_day_start(start_date) if start_date else None,
        end=local_day_end_exclusive(end_date) if end_date else None,
        customer_id=customer_id,
        keyword=keyword,
    )
    return SaleOrderPage(
        items=[_to_out(order) for order in rows],
        total=total,
        page=page,
        size=size,
        pages=calc_pages(total, size),
        total_amount=money(total_amount),
    )
