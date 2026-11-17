"""采购单 Schema。"""

from __future__ import annotations

from app.schemas.order import OrderCreateBase, OrderOutBase


class PurchaseOrderCreate(OrderCreateBase):
    """采购入库参数。partner_id 必须是供应商（supplier）。"""


class PurchaseOrderOut(OrderOutBase):
    """采购单详情。"""
