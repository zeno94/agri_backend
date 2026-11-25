"""功能模块配置接口（仅管理员）。"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import CurrentBoss, DbSession
from app.schemas.module import ModuleAdminOut, ModuleUpdate
from app.services import audit as audit_service
from app.services import module as module_service

router = APIRouter(prefix="/modules", tags=["功能模块"])


@router.get("", response_model=list[ModuleAdminOut], summary="全部功能模块")
async def list_modules(db: DbSession, _current_boss: CurrentBoss) -> list[ModuleAdminOut]:
    return await module_service.list_modules(db)


@router.put("/{module_id}", response_model=ModuleAdminOut, summary="修改功能模块配置")
async def update_module(
    module_id: int,
    payload: ModuleUpdate,
    request: Request,
    db: DbSession,
    current_boss: CurrentBoss,
) -> ModuleAdminOut:
    result = await module_service.update_module(db, module_id, payload)
    await audit_service.record(
        db,
        user=current_boss,
        action="module.update",
        module="modules",
        resource_type="module",
        resource_id=module_id,
        method="PUT",
        path=request.url.path,
        detail=payload.model_dump(exclude_unset=True),
        request=request,
    )
    return result
