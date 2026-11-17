"""老板看板 Schema。"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import UTCDateTime


class TopPartOut(BaseModel):
    part_id: int
    part_name: str
    quantity: int = Field(..., description="销售数量合计")


class DashboardOut(BaseModel):
    today_sales_amount: Decimal = Field(..., description="今日销售额（按服务器配置时区计算自然日）")
    month_sales_amount: Decimal = Field(..., description="本月销售额")
    today_order_count: int = Field(..., description="今日已完成销售单数")
    month_order_count: int = Field(..., description="本月已完成销售单数")
    top_parts: list[TopPartOut] = Field(..., description="本月销量 Top 5 配件")
    generated_at: UTCDateTime = Field(..., description="统计生成时间（UTC）")
