"""审计日志响应 Schema。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import UTCDateTime


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None = Field(..., description="操作人 ID；系统/失败登录可能为空")
    username: str = Field(..., description="操作人账号快照")
    role: str = Field(..., description="操作人角色快照")
    action: str = Field(..., description="业务动作编码")
    module: str = Field(..., description="所属模块")
    resource_type: str | None = Field(default=None, description="资源类型")
    resource_id: int | None = Field(default=None, description="资源 ID")
    method: str | None = None
    path: str | None = None
    status_code: int
    success: bool
    error_code: str | None = None
    detail: dict[str, Any] | None = Field(default=None, description="脱敏后的操作明细")
    ip: str | None = None
    user_agent: str | None = None
    request_id: str | None = None
    duration_ms: int | None = None
    created_at: UTCDateTime


class AuditLogPageQuery(BaseModel):
    """仅作文档说明；FastAPI 实际使用 Query 参数。"""

    page: int = 1
    page_size: int = 20
    action: str | None = None
    module: str | None = None
    username: str | None = None
    success: bool | None = None
