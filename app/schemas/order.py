"""采购单 / 销售单共用的明细与单据 Schema。"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import OrderStatus
from app.schemas.common import UTCDateTime


class OrderItemIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    part_id: int = Field(..., gt=0, description="配件 ID")
    quantity: int = Field(..., gt=0, le=1_000_000, description="数量")
    price: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
        description="成交单价；不传则采购单取配件采购价、销售单取销售价",
    )


class OrderCreateBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    partner_id: int = Field(..., gt=0, description="往来单位 ID")
    items: list[OrderItemIn] = Field(..., min_length=1, max_length=100, description="单据明细，至少一条")
    remark: str | None = Field(default=None, max_length=255, description="备注")

    @model_validator(mode="after")
    def _reject_duplicate_parts(self) -> OrderCreateBase:
        """同一单据内同一配件只允许出现一次，避免加锁顺序与汇总口径歧义。"""
        seen: set[int] = set()
        duplicated: set[int] = set()
        for item in self.items:
            if item.part_id in seen:
                duplicated.add(item.part_id)
            seen.add(item.part_id)
        if duplicated:
            raise ValueError(f"同一单据中配件不能重复，请合并数量：part_id={sorted(duplicated)}")
        return self


class OrderItemOut(BaseModel):
    part_id: int
    part_name: str
    quantity: int
    price: Decimal
    amount: Decimal = Field(..., description="小计金额 = price * quantity")


class OrderOutBase(BaseModel):
    id: int
    order_no: str
    partner_id: int
    partner_name: str
    total_amount: Decimal
    status: OrderStatus
    operator_id: int
    operator_name: str
    remark: str | None = None
    created_at: UTCDateTime
    items: list[OrderItemOut]
