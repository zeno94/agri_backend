"""客户 Schema。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import UTCDateTime


class CustomerBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    city: str = Field(default="开封市", max_length=50)
    county: str = Field(default="杞县", max_length=50)
    town: str | None = Field(default=None, max_length=50)
    village: str | None = Field(default=None, max_length=50)
    customer_type: str = Field(default="其他", max_length=30)
    acreage: Decimal = Field(default=Decimal("0.0"), ge=0, max_digits=8, decimal_places=1)
    main_crops: list[str] = Field(default_factory=lambda: ["其他"])
    tags: list[str] = Field(default_factory=lambda: ["其他"])
    note: str | None = Field(default=None, max_length=500)
    next_follow_up_at: datetime | None = None
    is_active: bool = True


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    city: str | None = Field(default=None, max_length=50)
    county: str | None = Field(default=None, max_length=50)
    town: str | None = Field(default=None, max_length=50)
    village: str | None = Field(default=None, max_length=50)
    customer_type: str | None = Field(default=None, max_length=30)
    acreage: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=1)
    main_crops: list[str] | None = None
    tags: list[str] | None = None
    note: str | None = Field(default=None, max_length=500)
    next_follow_up_at: datetime | None = None
    is_active: bool | None = None


class CustomerStats(BaseModel):
    order_count: int = 0
    total_amount: Decimal = Decimal("0.00")
    avg_order_amount: Decimal = Decimal("0.00")
    first_order_at: UTCDateTime | None = None
    last_order_at: UTCDateTime | None = None


class CustomerOut(CustomerBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: UTCDateTime
    updated_at: UTCDateTime
    stats: CustomerStats = Field(default_factory=CustomerStats)


class CustomerOptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str | None = None
    city: str | None = None
    county: str | None = None
    town: str | None = None
    village: str | None = None
    display_name: str = ""


class FollowupCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    method: str = Field(default="电话", max_length=20)
    content: str = Field(..., min_length=1, max_length=500)
    next_follow_up_at: datetime | None = None


class FollowupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    operator_id: int
    operator_name: str = ""
    method: str
    content: str
    next_follow_up_at: UTCDateTime | None = None
    created_at: UTCDateTime


class CustomerDetailOut(CustomerOut):
    followups: list[FollowupOut] = Field(default_factory=list)
    recent_orders: list[dict] = Field(default_factory=list)
