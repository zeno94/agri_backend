"""用户管理服务（管理员创建普通用户并分配模块）。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.security import hash_password
from app.crud import module as crud_module
from app.crud import user as crud_user
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.module import ModuleOut
from app.schemas.user import UserCreate, UserOut, UserUpdate

DEFAULT_EMPLOYEE_MODULES = ["parts", "purchase", "sale", "sales", "customers", "warning"]


def _build_user_out(user: User, modules) -> UserOut:
    is_boss = user.role == UserRole.BOSS.value
    return UserOut(
        id=user.id,
        username=user.username,
        role=UserRole(user.role),
        is_active=user.is_active,
        modules=[
            ModuleOut.model_validate(m)
            for m in modules
            if m.is_active and (is_boss or not m.is_admin_only)
        ],
        created_at=user.created_at,
    )


def user_out(user: User) -> UserOut:
    return _build_user_out(user, user.modules or [])


async def list_users(db: AsyncSession) -> list[UserOut]:
    users = await crud_user.list_users(db)
    all_modules = await crud_module.list_modules(db, active_only=True)
    return [
        _build_user_out(user, all_modules if user.role == UserRole.BOSS.value else user.modules or [])
        for user in users
    ]


async def _resolve_modules(db: AsyncSession, codes: list[str]) -> list:
    unique = list(dict.fromkeys(code.strip() for code in codes if code.strip()))
    modules = []
    for code in unique:
        module = await crud_module.get_by_code(db, code)
        if module is None:
            raise AppError("MODULE_NOT_FOUND", f"功能模块不存在：{code}", 400)
        if not module.is_active:
            raise AppError("MODULE_INACTIVE", f"功能模块已停用：{module.name}", 400)
        if module.is_admin_only:
            raise AppError("MODULE_ADMIN_ONLY", f"管理员模块不能分配给普通用户：{module.name}", 400)
        modules.append(module)
    return modules


async def create_user(db: AsyncSession, payload: UserCreate) -> UserOut:
    username = payload.username.strip()
    if await crud_user.get_by_username(db, username) is not None:
        raise AppError("USERNAME_EXISTS", "登录账号已存在", 409)

    codes = payload.module_codes or DEFAULT_EMPLOYEE_MODULES
    modules = await _resolve_modules(db, codes)
    user = User(
        username=username,
        password_hash=hash_password(payload.password),
        role=UserRole.EMPLOYEE.value,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    await crud_module.set_user_modules(db, user.id, [m.id for m in modules])
    user_id = user.id
    await db.commit()
    db.expire(user, ["modules"])
    user = await crud_user.get_by_id(db, user_id)
    assert user is not None
    return user_out(user)


async def update_user(db: AsyncSession, user_id: int, payload: UserUpdate) -> UserOut:
    user = await crud_user.get_by_id(db, user_id)
    if user is None:
        raise AppError("USER_NOT_FOUND", "用户不存在", 404)
    if user.role == UserRole.BOSS.value:
        raise AppError("ADMIN_PROTECTED", "不能修改管理员账号", 400)

    values = payload.model_dump(exclude_unset=True)
    if "username" in values:
        new_username = values["username"].strip()
        if new_username != user.username:
            exists = await crud_user.get_by_username(db, new_username)
            if exists is not None:
                raise AppError("USERNAME_EXISTS", "登录账号已存在", 409)
            user.username = new_username
    if "is_active" in values:
        user.is_active = bool(values["is_active"])
    await db.commit()
    db.expire(user, ["modules"])
    refreshed = await crud_user.get_by_id(db, user_id)
    assert refreshed is not None
    return user_out(refreshed)


async def set_modules(db: AsyncSession, user_id: int, codes: list[str]) -> UserOut:
    user = await crud_user.get_by_id(db, user_id)
    if user is None:
        raise AppError("USER_NOT_FOUND", "用户不存在", 404)
    if user.role == UserRole.BOSS.value:
        raise AppError("ADMIN_PROTECTED", "管理员默认拥有全部模块，无需分配", 400)

    modules = await _resolve_modules(db, codes)
    await crud_module.set_user_modules(db, user.id, [m.id for m in modules])
    await db.commit()
    db.expire(user, ["modules"])
    user = await crud_user.get_by_id(db, user_id)
    assert user is not None
    return user_out(user)


async def reset_password(db: AsyncSession, user_id: int, password: str) -> None:
    user = await crud_user.get_by_id(db, user_id)
    if user is None:
        raise AppError("USER_NOT_FOUND", "用户不存在", 404)
    if user.role == UserRole.BOSS.value:
        raise AppError("ADMIN_PROTECTED", "管理员密码请使用运维脚本重置", 400)
    user.password_hash = hash_password(password)
    await db.commit()


async def get_profile(db: AsyncSession, user: User) -> UserOut:
    latest = await crud_user.get_by_id(db, user.id)
    assert latest is not None
    if latest.role == UserRole.BOSS.value:
        modules = await crud_module.list_modules(db, active_only=True)
        return _build_user_out(latest, modules)
    return user_out(latest)


def user_has_module(user: User, code: str) -> bool:
    if user.role == UserRole.BOSS.value:
        return True
    return any(module.code == code and module.is_active for module in (user.modules or []))
