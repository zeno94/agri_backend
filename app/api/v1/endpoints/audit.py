"""操作日志查询接口。

数据范围：
- boss：可看全部日志，并可按 username 过滤；
- employee：只能看自己的日志，尝试按他人 username 过滤会得到 403；
- 日志接口本身也会记录一条 audit.view。
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import CurrentUser, DbSession, require_module
from app.schemas.audit import AuditLogOut
from app.schemas.common import Page
from app.services import audit as audit_service

router = APIRouter(prefix="/audit", tags=["操作日志"], dependencies=[Depends(require_module("audit"))])


@router.get(
    "/logs",
    response_model=Page[AuditLogOut],
    summary="操作日志分页查询",
    description="boss 可查看全部；employee 仅能查看自己的操作记录。",
)
async def list_audit_logs(
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="每页数量")] = 20,
    action: Annotated[str | None, Query(max_length=50, description="动作编码，如 sale.outbound")] = None,
    module: Annotated[str | None, Query(max_length=30, description="模块，如 sales")] = None,
    username: Annotated[str | None, Query(max_length=50, description="仅 boss 可用")] = None,
    success: Annotated[bool | None, Query(description="true 成功 / false 失败")] = None,
    start_date: Annotated[date | None, Query(description="开始日期（含，Asia/Shanghai）")] = None,
    end_date: Annotated[date | None, Query(description="结束日期（含，Asia/Shanghai）")] = None,
) -> Page[AuditLogOut]:
    result = await audit_service.list_logs(
        db,
        current_user,
        page=page,
        size=page_size,
        action=action,
        module=module,
        username=username,
        success=success,
        start_date=start_date,
        end_date=end_date,
    )

    await audit_service.record(
        db,
        user=current_user,
        action="audit.view",
        module="audit",
        method="GET",
        path=request.url.path,
        detail={
            "page": page,
            "page_size": page_size,
            "action": action,
            "module": module,
            "username": username,
            "success": success,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
        },
        request=request,
        commit=True,
    )
    return result


@router.get(
    "/logs/{log_id}",
    response_model=AuditLogOut,
    summary="操作日志详情",
    description="boss 可查看任意日志；employee 只能查看自己的日志，他人日志返回 404。",
)
async def get_audit_log(
    log_id: int,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
) -> AuditLogOut:
    result = await audit_service.get_log(db, current_user, log_id)
    await audit_service.record(
        db,
        user=current_user,
        action="audit.view",
        module="audit",
        resource_type="audit_log",
        resource_id=log_id,
        method="GET",
        path=request.url.path,
        request=request,
        commit=True,
    )
    return result
