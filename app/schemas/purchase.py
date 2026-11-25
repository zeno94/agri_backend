"""采购单 Schema。"""

from __future__ import annotations

from pydantic import AliasChoices, Field

from app.schemas.order import OrderCreateBase, OrderOutBase


class PurchaseOrderCreate(OrderCreateBase):
    """采购入库参数。supplier_id 必须是供应商。"""

    supplier_id: int = Field(
        ...,
        gt=0,
        validation_alias=AliasChoices("supplier_id", "partner_id"),
        description="供应商 ID；兼容旧字段 partner_id",
    )


class PurchaseOrderOut(OrderOutBase):
    """采购单详情。"""

    supplier_id: int
    supplier_name: str
