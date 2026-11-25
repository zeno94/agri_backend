"""供应商 Schema。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import UTCDateTime


class SupplierBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=200)
    contact_person: str | None = Field(default=None, max_length=50)
    main_categories: list[str] = Field(default_factory=list)
    delivery_days: int | None = Field(default=None, ge=0, le=365)
    payment_terms: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=500)
    is_active: bool = True

    @field_validator("main_categories", mode="before")
    @classmethod
    def _default_categories(cls, value):
        return value or []


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=200)
    contact_person: str | None = Field(default=None, max_length=50)
    main_categories: list[str] | None = None
    delivery_days: int | None = Field(default=None, ge=0, le=365)
    payment_terms: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class SupplierOut(SupplierBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: UTCDateTime
    updated_at: UTCDateTime


class SupplierListItem(SupplierOut):
    order_count: int = 0
    total_amount: Decimal = Decimal("0.00")
    last_order_at: datetime | None = None


class SupplierOptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str | None = None
    address: str | None = None
