"""用户操作审计日志。

记录登录/退出、主数据写操作、采购/销售、看板与日志查看等业务动作。
日志只追加，不提供更新/删除 API；用户名与角色做快照，用户删除后仍可追溯。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, big_int_pk, utcnow


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_user_created_at", "user_id", "created_at"),
        Index("ix_audit_logs_action_created_at", "action", "created_at"),
        Index("ix_audit_logs_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(big_int_pk(), primary_key=True, autoincrement=True)
    # 新库 users.id 为 BIGINT；历史库可能是 INT。
    # 0002 迁移会按库里 users.id 的实际类型建列，运行时 Python int 两者都兼容。
    user_id: Mapped[int | None] = mapped_column(
        big_int_pk(),
        nullable=True,
        index=True,
    )
    # 用户信息快照：用户被删除/改名后仍可追溯
    username: Mapped[str] = mapped_column(String(50), nullable=False, default="", server_default="")
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="", server_default="")

    action: Mapped[str] = mapped_column(String(50), nullable=False, comment="业务动作，如 sale.outbound")
    module: Mapped[str] = mapped_column(String(30), nullable=False, default="", server_default="")
    resource_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    resource_id: Mapped[int | None] = mapped_column(big_int_pk(), nullable=True)

    method: Mapped[str | None] = mapped_column(String(10), nullable=True)
    path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False, default=200, server_default="200")
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow,
        server_default=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<AuditLog id={self.id} user={self.username!r} " f"action={self.action!r} success={self.success}>"
