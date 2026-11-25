"""功能模块与用户模块授权数据访问。"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.module import Module, UserModule


async def list_modules(db: AsyncSession, *, active_only: bool = False) -> list[Module]:
    stmt = select(Module).order_by(Module.sort_order.asc(), Module.id.asc())
    if active_only:
        stmt = stmt.where(Module.is_active.is_(True))
    rows = await db.scalars(stmt)
    return list(rows.all())


async def get_by_id(db: AsyncSession, module_id: int) -> Module | None:
    return await db.get(Module, module_id)


async def get_by_code(db: AsyncSession, code: str) -> Module | None:
    return await db.scalar(select(Module).where(Module.code == code))


async def modules_for_user(db: AsyncSession, user_id: int) -> list[Module]:
    rows = await db.scalars(
        select(Module)
        .join(UserModule, UserModule.module_id == Module.id)
        .where(UserModule.user_id == user_id, Module.is_active.is_(True))
        .order_by(Module.sort_order.asc(), Module.id.asc())
    )
    return list(rows.all())


async def user_has_module(db: AsyncSession, user_id: int, code: str) -> bool:
    return bool(
        await db.scalar(
            select(Module.id)
            .join(UserModule, UserModule.module_id == Module.id)
            .where(
                UserModule.user_id == user_id,
                Module.code == code,
                Module.is_active.is_(True),
                Module.is_admin_only.is_(False),
            )
            .limit(1)
        )
    )


async def set_user_modules(db: AsyncSession, user_id: int, module_ids: list[int]) -> None:
    await db.execute(delete(UserModule).where(UserModule.user_id == user_id))
    for module_id in sorted(set(module_ids)):
        db.add(UserModule(user_id=user_id, module_id=module_id))
    await db.flush()
