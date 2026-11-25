"""用户与权限相关 Schema。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import UserRole
from app.schemas.common import UTCDateTime
from app.schemas.module import ModuleOut


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="用户 ID")
    username: str = Field(..., description="登录账号")
    role: UserRole = Field(..., description="角色：boss / employee")
    is_active: bool = Field(..., description="账号是否启用")
    modules: list[ModuleOut] = Field(default_factory=list, description="当前用户可用模块")
    created_at: UTCDateTime = Field(..., description="创建时间（UTC）")


class UserCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(..., min_length=8, max_length=128)
    module_codes: list[str] = Field(default_factory=list, max_length=30)


class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    is_active: bool | None = None


class UserModulesUpdate(BaseModel):
    module_codes: list[str] = Field(default_factory=list, max_length=30)


class PasswordReset(BaseModel):
    password: str = Field(..., min_length=8, max_length=128)
