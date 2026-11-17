"""通用 Schema：分页、UTC 时间序列化、错误响应。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, Generic, TypeVar

from pydantic import BaseModel, Field, PlainSerializer

T = TypeVar("T")


def _serialize_utc(value: datetime) -> str:
    """数据库中的 naive UTC 时间在输出时补上 +00:00，前端可无损转本地时区。"""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat(timespec="seconds")


UTCDateTime = Annotated[datetime, PlainSerializer(_serialize_utc, return_type=str)]


class Page(BaseModel, Generic[T]):
    """统一分页响应。"""

    items: list[T] = Field(default_factory=list, description="当前页数据")
    total: int = Field(..., ge=0, description="总记录数")
    page: int = Field(..., ge=1, description="当前页码")
    size: int = Field(..., ge=1, description="每页数量")
    pages: int = Field(..., ge=0, description="总页数")


class Message(BaseModel):
    message: str


class ErrorBody(BaseModel):
    """错误响应文档模型（实际返回由全局异常处理器生成）。"""

    code: str
    message: str
    detail: Any | None = None
