"""功能模块配置服务。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.crud import module as crud_module
from app.models.module import Module
from app.schemas.module import ModuleAdminOut, ModuleOut, ModuleUpdate


def module_out(module: Module) -> ModuleOut:
    return ModuleOut.model_validate(module)


def module_admin_out(module: Module) -> ModuleAdminOut:
    return ModuleAdminOut.model_validate(module)


async def list_modules(db: AsyncSession, *, active_only: bool = False) -> list[ModuleAdminOut]:
    return [module_admin_out(m) for m in await crud_module.list_modules(db, active_only=active_only)]


async def update_module(db: AsyncSession, module_id: int, payload: ModuleUpdate) -> ModuleAdminOut:
    module = await crud_module.get_by_id(db, module_id)
    if module is None:
        raise AppError("MODULE_NOT_FOUND", "功能模块不存在", 404)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(module, key, value)
    await db.commit()
    await db.refresh(module)
    return module_admin_out(module)
