"""往来单位 Schema。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import PartnerType
from app.schemas.common import UTCDateTime


class PartnerBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=100, description="单位名称")
    type: PartnerType = Field(..., description="类型：supplier 供应商 / customer 客户")
    phone: str | None = Field(default=None, max_length=30, description="联系电话")


class PartnerCreate(PartnerBase):
    pass


class PartnerOut(PartnerBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: UTCDateTime
    updated_at: UTCDateTime
