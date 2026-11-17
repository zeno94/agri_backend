"""用户相关 Schema。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import UserRole
from app.schemas.common import UTCDateTime


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="用户 ID")
    username: str = Field(..., description="登录账号")
    role: UserRole = Field(..., description="角色：boss / employee")
    is_active: bool = Field(..., description="账号是否启用")
    created_at: UTCDateTime = Field(..., description="创建时间（UTC）")
