"""配件相关 Schema。"""

from __future__ import annotations

from decimal import Decimal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import UTCDateTime


class PartBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=100, description="配件名称", examples=["柴油滤清器"])
    model: str = Field(..., min_length=1, max_length=100, description="适配型号", examples=["4L88"])
    category: str = Field(..., min_length=1, max_length=50, description="配件分类", examples=["滤清器"])
    brand: str = Field(default="", max_length=50, description="品牌", examples=["潍柴"])
    stock: int = Field(default=0, ge=0, le=100_000_000, description="当前库存")
    safe_stock: int = Field(default=0, ge=0, le=100_000_000, description="安全库存（低于等于此值触发预警）")
    # 前端新增配件只填写销售价，采购价可在后续采购/编辑时补充
    purchase_price: Decimal = Field(
        default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2, description="采购价（前端未传时为 0）"
    )
    sale_price: Decimal = Field(
        ...,
        ge=0,
        max_digits=12,
        decimal_places=2,
        validation_alias=AliasChoices("sale_price", "price"),
        description="销售价；兼容前端字段 price",
    )


class PartCreate(PartBase):
    """新增配件；stock 大于 0 时会生成一条「期初盘点」库存流水。"""


class PartUpdate(BaseModel):
    """修改配件，所有字段可选；未传字段保持原值。"""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=100)
    model: str | None = Field(default=None, min_length=1, max_length=100)
    category: str | None = Field(default=None, min_length=1, max_length=50)
    brand: str | None = Field(default=None, max_length=50)
    stock: int | None = Field(default=None, ge=0, le=100_000_000)
    safe_stock: int | None = Field(default=None, ge=0, le=100_000_000)
    purchase_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    sale_price: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
        validation_alias=AliasChoices("sale_price", "price"),
    )

    @model_validator(mode="after")
    def _require_at_least_one_field(self) -> PartUpdate:
        if not self.model_fields_set:
            raise ValueError("至少需要提供一个待更新字段")
        return self


class PartOut(PartBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: UTCDateTime
    updated_at: UTCDateTime


class PartWarningOut(PartOut):
    shortage: int = Field(..., ge=0, description="建议补货数量 = 安全库存 - 当前库存")
