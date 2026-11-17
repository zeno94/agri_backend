"""销售单 Schema。"""

from __future__ import annotations

from app.schemas.order import OrderCreateBase, OrderOutBase


class SaleOrderCreate(OrderCreateBase):
    """销售出库参数。partner_id 必须是客户（customer）。"""


class SaleOrderOut(OrderOutBase):
    """销售单详情。"""
