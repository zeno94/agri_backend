"""审计日志数据访问。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


async def list_logs(
    db: AsyncSession,
    *,
    page: int,
    size: int,
    user_id: int | None = None,
    username: str | None = None,
    action: str | None = None,
    module: str | None = None,
    success: bool | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> tuple[list[AuditLog], int]:
    conditions = []
    if user_id is not None:
        conditions.append(AuditLog.user_id == user_id)
    if username:
        conditions.append(AuditLog.username == username)
    if action:
        conditions.append(AuditLog.action == action)
    if module:
        conditions.append(AuditLog.module == module)
    if success is not None:
        conditions.append(AuditLog.success.is_(success))
    if start is not None:
        conditions.append(AuditLog.created_at >= start)
    if end is not None:
        conditions.append(AuditLog.created_at < end)

    total = await db.scalar(select(func.count(AuditLog.id)).where(*conditions)) or 0
    rows = await db.scalars(
        select(AuditLog)
        .where(*conditions)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    return list(rows.all()), total


async def get_by_id(db: AsyncSession, log_id: int) -> AuditLog | None:
    return await db.get(AuditLog, log_id)
