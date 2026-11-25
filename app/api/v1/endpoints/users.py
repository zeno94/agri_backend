"""用户管理接口（仅管理员）。"""

from __future__ import annotations

from fastapi import APIRouter, Request, status

from app.api.deps import CacheClient, CurrentBoss, DbSession
from app.core import revocation
from app.schemas.common import Message
from app.schemas.user import (
    PasswordReset,
    UserCreate,
    UserModulesUpdate,
    UserOut,
    UserUpdate,
)
from app.services import audit as audit_service
from app.services import user as user_service

router = APIRouter(prefix="/users", tags=["用户管理"])


@router.get("", response_model=list[UserOut], summary="用户列表")
async def list_users(db: DbSession, _current_boss: CurrentBoss) -> list[UserOut]:
    return await user_service.list_users(db)


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED, summary="创建普通用户")
async def create_user(payload: UserCreate, request: Request, db: DbSession, current_boss: CurrentBoss) -> UserOut:
    result = await user_service.create_user(db, payload)
    await audit_service.record(
        db,
        user=current_boss,
        action="user.create",
        module="users",
        resource_type="user",
        resource_id=result.id,
        method="POST",
        path=request.url.path,
        detail={
            "username": result.username,
            "modules": [module.code for module in result.modules],
        },
        request=request,
    )
    return result


@router.patch("/{user_id}", response_model=UserOut, summary="修改用户状态/账号")
async def update_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    db: DbSession,
    current_boss: CurrentBoss,
    cache: CacheClient,
) -> UserOut:
    result = await user_service.update_user(db, user_id, payload)
    # 停用账号的同时吊销该用户已签发的全部 Token，避免「停用了但凭证还能用」
    changes = payload.model_dump(exclude_unset=True)
    tokens_revoked = False
    if changes.get("is_active") is False:
        tokens_revoked = await revocation.revoke_user_tokens(cache, user_id)
    await audit_service.record(
        db,
        user=current_boss,
        action="user.update",
        module="users",
        resource_type="user",
        resource_id=user_id,
        method="PATCH",
        path=request.url.path,
        detail={**changes, "tokens_revoked": tokens_revoked},
        request=request,
    )
    return result


@router.put("/{user_id}/modules", response_model=UserOut, summary="分配用户可用模块")
async def set_user_modules(
    user_id: int,
    payload: UserModulesUpdate,
    request: Request,
    db: DbSession,
    current_boss: CurrentBoss,
) -> UserOut:
    result = await user_service.set_modules(db, user_id, payload.module_codes)
    await audit_service.record(
        db,
        user=current_boss,
        action="user.modules",
        module="users",
        resource_type="user",
        resource_id=user_id,
        method="PUT",
        path=request.url.path,
        detail={"module_codes": payload.module_codes},
        request=request,
    )
    return result


@router.post("/{user_id}/reset-password", response_model=Message, summary="重置普通用户密码")
async def reset_password(
    user_id: int,
    payload: PasswordReset,
    request: Request,
    db: DbSession,
    current_boss: CurrentBoss,
    cache: CacheClient,
) -> Message:
    await user_service.reset_password(db, user_id, payload.password)
    # 改密后旧 Token 必须立刻失效，否则「改了密码但别人手上的凭证还能用」
    tokens_revoked = await revocation.revoke_user_tokens(cache, user_id)
    await audit_service.record(
        db,
        user=current_boss,
        action="user.password_reset",
        module="users",
        resource_type="user",
        resource_id=user_id,
        method="POST",
        path=request.url.path,
        detail={"username": f"user#{user_id}", "tokens_revoked": tokens_revoked},
        request=request,
    )
    return Message(message="密码已重置，该账号的历史登录凭证已失效")
