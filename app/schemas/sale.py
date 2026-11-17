"""销售单 Schema。"""

from __future__ import annotations

from typing import Any

from pydantic import model_validator

from app.schemas.order import OrderCreateBase, OrderOutBase


class SaleOrderCreate(OrderCreateBase):
    """销售出库参数。partner_id 必须是客户（customer）。

    兼容两种前端/客户端格式：
    1. 多明细：{"customer_id": 1, "items": [{"part_id": 2, "quantity": 3}]}
    2. 单条（现有 Vue 页面）：{"customer_id": 1, "part_id": 2, "quantity": 3}
    单条格式会在校验前转换成统一的 items 结构，业务层无需分支。
    """

    @model_validator(mode="before")
    @classmethod
    def _normalize_single_item_payload(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        payload = dict(data)
        if isinstance(payload.get("items"), dict):
            payload["items"] = [payload["items"]]

        if not payload.get("items") and payload.get("part_id") is not None:
            item: dict[str, Any] = {
                "part_id": payload["part_id"],
                "quantity": payload.get("quantity"),
            }
            unit_price = payload.get("unit_price", payload.get("price"))
            if unit_price is not None:
                item["price"] = unit_price
            payload["items"] = [item]
        return payload


class SaleOrderOut(OrderOutBase):
    """销售单详情。"""
