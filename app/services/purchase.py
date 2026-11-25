"""采购入库服务。

事务流程：
1. 校验供应商；
2. 按 part_id 升序 SELECT ... FOR UPDATE 锁定所有配件行；
3. 逐条增加库存、写采购明细、写库存流水（in，正数）；
4. 汇总金额、单据置为 completed，一次 commit。
任一步失败则整体回滚，不产生半张单或半次库存变更。
"""

from __future__ import annotations

from decimal import Decimal

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import invalidate_parts_cache
from app.core.exceptions import AppError
from app.core.money import generate_order_no, money
from app.crud import order as crud_order
from app.crud import part as crud_part
from app.crud import supplier as crud_supplier
from app.models.enums import ChangeType, OrderStatus
from app.models.inventory_log import InventoryLog
from app.models.purchase import PurchaseItem, PurchaseOrder
from app.models.user import User
from app.schemas.common import Page
from app.schemas.order import OrderItemOut
from app.schemas.purchase import PurchaseOrderCreate, PurchaseOrderOut
from app.services.common import calc_pages


def _to_out(order: PurchaseOrder) -> PurchaseOrderOut:
    return PurchaseOrderOut(
        id=order.id,
        order_no=order.order_no,
        supplier_id=order.supplier_id,
        supplier_name=order.supplier.name if order.supplier is not None else "",
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


async def create_inbound(
    db: AsyncSession,
    redis: Redis | None,
    payload: PurchaseOrderCreate,
    operator: User,
) -> PurchaseOrderOut:
    supplier = await crud_supplier.get_by_id(db, payload.supplier_id)
    if supplier is None or not supplier.is_active:
        raise AppError("SUPPLIER_NOT_FOUND", "供应商不存在或已停用", 404)

    order_id: int | None = None
    try:
        # 固定加锁顺序，避免采购与销售并发时互相等待形成死锁
        parts = await crud_part.lock_parts_by_ids(db, [item.part_id for item in payload.items])
        missing = sorted({item.part_id for item in payload.items} - parts.keys())
        if missing:
            raise AppError("PART_NOT_FOUND", "部分配件不存在", 404, detail={"part_ids": missing})

        order = PurchaseOrder(
            order_no=generate_order_no("PO"),
            supplier_id=supplier.id,
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
            unit_price = money(item.price if item.price is not None else part.purchase_price)
            before_stock = part.stock
            part.stock = before_stock + item.quantity

            db.add(
                PurchaseItem(
                    order_id=order.id,
                    part_id=part.id,
                    quantity=item.quantity,
                    price=unit_price,
                )
            )
            db.add(
                InventoryLog(
                    part_id=part.id,
                    change_type=ChangeType.IN.value,
                    change_qty=item.quantity,
                    before_stock=before_stock,
                    after_stock=part.stock,
                    operator_id=operator.id,
                    remark=f"采购入库 {order.order_no}",
                )
            )
            total_amount += unit_price * item.quantity

        order.total_amount = money(total_amount)
        await db.commit()
        order_id = order.id
    except Exception:
        await db.rollback()
        raise

    await invalidate_parts_cache(redis)

    detail = await crud_order.get_purchase_detail(db, order_id)
    if detail is None:  # pragma: no cover - 正常流程不可能出现
        raise AppError("ORDER_NOT_FOUND", "采购单创建后查询失败", 500)
    return _to_out(detail)


async def list_inbound_orders(db: AsyncSession, *, page: int, size: int) -> Page[PurchaseOrderOut]:
    rows, total = await crud_order.list_purchase_orders(db, page=page, size=size)
    return Page[PurchaseOrderOut](
        items=[_to_out(order) for order in rows],
        total=total,
        page=page,
        size=size,
        pages=calc_pages(total, size),
    )
