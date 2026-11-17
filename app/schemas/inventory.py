"""库存流水 Schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.enums import ChangeType
from app.schemas.common import UTCDateTime


class InventoryLogOut(BaseModel):
    id: int
    part_id: int
    part_name: str
    change_type: ChangeType
    change_qty: int = Field(..., description="带符号变动数量：入库为正、出库为负")
    before_stock: int
    after_stock: int
    operator_id: int
    operator_name: str
    remark: str | None = None
    created_at: UTCDateTime
