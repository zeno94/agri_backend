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

from decimal import Decimal

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import invalidate_parts_cache
from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.core.money import generate_order_no, money
from app.crud import order as crud_order
from app.crud import part as crud_part
from app.crud import partner as crud_partner
from app.models.enums import ChangeType, OrderStatus, PartnerType
from app.models.inventory_log import InventoryLog
from app.models.sale import SaleItem, SaleOrder
from app.models.user import User
from app.schemas.common import Page
from app.schemas.order import OrderItemOut
from app.schemas.sale import SaleOrderCreate, SaleOrderOut
from app.services.common import calc_pages

logger = get_logger(__name__)


def _to_out(order: SaleOrder) -> SaleOrderOut:
    return SaleOrderOut(
        id=order.id,
        order_no=order.order_no,
        partner_id=order.partner_id,
        partner_name=order.partner.name if order.partner is not None else "",
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
    partner = await crud_partner.get_by_id(db, payload.partner_id)
    if partner is None:
        raise AppError("PARTNER_NOT_FOUND", "往来单位不存在", 404)
    if partner.type != PartnerType.CUSTOMER.value:
        raise AppError("PARTNER_TYPE_INVALID", "销售出库的往来单位必须是客户", 400)

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
            logger.warning("销售出库库存不足，整单回滚：operator=%s partner=%s", operator.id, partner.id)
            raise AppError(
                "INSUFFICIENT_STOCK",
                "库存不足，销售单已回滚",
                409,
                detail={"items": shortages},
            )

        # 3) 校验通过后创建单据并统一扣减库存
        order = SaleOrder(
            order_no=generate_order_no("SO"),
            partner_id=partner.id,
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


async def list_outbound_orders(db: AsyncSession, *, page: int, size: int) -> Page[SaleOrderOut]:
    rows, total = await crud_order.list_sale_orders(db, page=page, size=size)
    return Page[SaleOrderOut](
        items=[_to_out(order) for order in rows],
        total=total,
        page=page,
        size=size,
        pages=calc_pages(total, size),
    )
