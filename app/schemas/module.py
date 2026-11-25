"""功能模块 Schema。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import UTCDateTime


class ModuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    path: str
    icon: str
    description: str | None = None
    sort_order: int
    is_active: bool
    is_admin_only: bool


class ModuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    icon: str | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=255)
    sort_order: int | None = Field(default=None, ge=0, le=9999)
    is_active: bool | None = None
    is_admin_only: bool | None = None


class ModuleAdminOut(ModuleOut):
    created_at: UTCDateTime
    updated_at: UTCDateTime
