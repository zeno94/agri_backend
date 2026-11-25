"""审计日志服务：写入、脱敏、分页查询与数据范围控制。"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.logging import get_logger, request_id_ctx
from app.core.time import local_day_end_exclusive, local_day_start
from app.crud import audit as crud_audit
from app.models.audit_log import AuditLog
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.audit import AuditLogOut
from app.schemas.common import Page
from app.services.common import calc_pages

logger = get_logger(__name__)

_SENSITIVE_KEYWORDS = ("password", "token", "secret", "authorization", "cookie")


def _sanitize(value: Any, depth: int = 0) -> Any:
    """递归脱敏并转换成可 JSON 序列化的结构。"""
    if depth > 8:
        return "***"
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if any(keyword in key_text.lower() for keyword in _SENSITIVE_KEYWORDS):
                result[key_text] = "***"
            else:
                result[key_text] = _sanitize(item, depth + 1)
        return result
    if isinstance(value, list | tuple | set):
        return [_sanitize(item, depth + 1) for item in value]
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "model_dump"):
        return _sanitize(value.model_dump(), depth + 1)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        return value[:1000]
    return value


async def record(
    db: AsyncSession,
    *,
    action: str,
    module: str,
    user: User | None = None,
    username: str | None = None,
    role: str | None = None,
    resource_type: str | None = None,
    resource_id: int | None = None,
    status_code: int = 200,
    success: bool = True,
    error_code: str | None = None,
    detail: Any | None = None,
    request: Request | None = None,
    method: str | None = None,
    path: str | None = None,
    duration_ms: int | None = None,
    commit: bool = True,
) -> AuditLog | None:
    """写一条审计日志。

    默认独立提交；审计写入失败只记录错误，不阻断业务响应。
    commit=False 时由调用方与业务事务一起提交。
    """
    user_id = user.id if user is not None else None
    snapshot_username = username if username is not None else (user.username if user else "")
    snapshot_role = role if role is not None else (user.role if user else "")

    ip = None
    user_agent = None
    request_id = request_id_ctx.get()
    if request is not None:
        ip = request.client.host if request.client is not None else None
        user_agent = request.headers.get("user-agent")
        if user_agent:
            user_agent = user_agent[:255]
        method = method or request.method
        path = path or request.url.path

    log = AuditLog(
        user_id=user_id,
        username=(snapshot_username or "")[:50],
        role=(snapshot_role or "")[:20],
        action=action[:50],
        module=module[:30],
        resource_type=(resource_type[:30] if resource_type else None),
        resource_id=resource_id,
        method=(method[:10] if method else None),
        path=(path[:255] if path else None),
        status_code=status_code,
        success=success,
        error_code=(error_code[:50] if error_code else None),
        detail=_sanitize(detail),
        ip=ip,
        user_agent=user_agent,
        request_id=(request_id if request_id and request_id != "-" else None),
        duration_ms=duration_ms,
    )

    try:
        db.add(log)
        if commit:
            await db.commit()
            await db.refresh(log)
        else:
            await db.flush()
    except SQLAlchemyError:
        await db.rollback()
        logger.exception(
            "审计日志写入失败：action=%s user=%s resource=%s/%s",
            action,
            snapshot_username,
            resource_type,
            resource_id,
        )
        return None
    return log


async def list_logs(
    db: AsyncSession,
    current_user: User,
    *,
    page: int,
    size: int,
    action: str | None = None,
    module: str | None = None,
    username: str | None = None,
    success: bool | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> Page[AuditLogOut]:
    if start_date and end_date and start_date > end_date:
        raise AppError("INVALID_DATE_RANGE", "开始日期不能晚于结束日期", 400)

    is_boss = current_user.role == UserRole.BOSS.value
    scoped_username: str | None = None
    scoped_user_id: int | None = None

    if is_boss:
        scoped_username = username
    else:
        if username and username != current_user.username:
            raise AppError("FORBIDDEN", "员工只能查看自己的操作日志", 403)
        scoped_user_id = current_user.id

    rows, total = await crud_audit.list_logs(
        db,
        page=page,
        size=size,
        user_id=scoped_user_id,
        username=scoped_username,
        action=action,
        module=module,
        success=success,
        start=local_day_start(start_date) if start_date else None,
        end=local_day_end_exclusive(end_date) if end_date else None,
    )

    return Page[AuditLogOut](
        items=[AuditLogOut.model_validate(row) for row in rows],
        total=total,
        page=page,
        size=size,
        pages=calc_pages(total, size),
    )


async def get_log(db: AsyncSession, current_user: User, log_id: int) -> AuditLogOut:
    log = await crud_audit.get_by_id(db, log_id)
    if log is None:
        raise AppError("AUDIT_LOG_NOT_FOUND", "操作日志不存在", 404)

    if current_user.role != UserRole.BOSS.value and log.user_id != current_user.id:
        # 不暴露他人日志是否存在
        raise AppError("AUDIT_LOG_NOT_FOUND", "操作日志不存在", 404)

    return AuditLogOut.model_validate(log)
