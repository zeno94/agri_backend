"""管理员看板 Schema。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import UTCDateTime


class TopPartOut(BaseModel):
    part_id: int
    part_name: str
    quantity: int = Field(..., description="销售数量合计")


class ReportPartOut(TopPartOut):
    """报表用配件排行：同时给出销量与销售额。"""

    amount: Decimal = Field(..., description="销售额合计")


class TopCustomerOut(BaseModel):
    customer_id: int
    customer_name: str
    amount: Decimal = Field(..., description="交易金额合计")
    order_count: int = Field(..., description="单据数")


class TopSupplierOut(BaseModel):
    supplier_id: int
    supplier_name: str
    amount: Decimal = Field(..., description="交易金额合计")
    order_count: int = Field(..., description="单据数")


class CategorySalesOut(BaseModel):
    category: str
    quantity: int = Field(..., description="销售数量合计")
    amount: Decimal = Field(..., description="销售额合计")


class TrendPointOut(BaseModel):
    period: str = Field(..., description="日：YYYY-MM-DD；月：YYYY-MM")
    sales_amount: Decimal = Field(..., description="销售额")
    order_count: int = Field(..., description="销售单数")


class DashboardOut(BaseModel):
    today_sales_amount: Decimal = Field(..., description="今日销售额（按服务器配置时区计算自然日）")
    month_sales_amount: Decimal = Field(..., description="本月销售额")
    today_order_count: int = Field(..., description="今日已完成销售单数")
    month_order_count: int = Field(..., description="本月已完成销售单数")
    top_parts: list[TopPartOut] = Field(..., description="本月销量 Top 5 配件")
    generated_at: UTCDateTime = Field(..., description="统计生成时间（UTC）")


class DashboardReportOut(BaseModel):
    """按任意业务日期区间聚合的经营报表。"""

    start_date: date = Field(..., description="业务时区开始日期（含）")
    end_date: date = Field(..., description="业务时区结束日期（含）")
    data_start_date: date | None = Field(None, description="库内最早销售日期")
    data_end_date: date | None = Field(None, description="库内最晚销售日期")

    sales_amount: Decimal = Field(..., description="销售额")
    sales_order_count: int = Field(..., description="销售单数")
    items_sold: int = Field(..., description="销售件数")
    avg_order_amount: Decimal = Field(..., description="平均客单价")
    purchase_amount: Decimal = Field(..., description="采购金额")
    purchase_order_count: int = Field(..., description="采购单数")
    gross_profit: Decimal = Field(..., description="销售毛利（销售额 - 参考进货成本）")
    gross_margin: Decimal = Field(..., description="毛利率（百分比，30.89 表示 30.89%）")

    top_parts: list[ReportPartOut] = Field(..., description="销售额 Top 5 配件")
    top_customers: list[TopCustomerOut] = Field(..., description="销售额 Top 5 客户")
    top_suppliers: list[TopSupplierOut] = Field(..., description="采购额 Top 5 供应商")
    category_breakdown: list[CategorySalesOut] = Field(..., description="分类销售占比")
    trend: list[TrendPointOut] = Field(..., description="销售趋势")
    trend_granularity: Literal["day", "month"] = Field(..., description="趋势粒度")
    generated_at: UTCDateTime = Field(..., description="统计生成时间（UTC）")
