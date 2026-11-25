"""API 依赖：数据库会话、Redis、当前用户与角色校验。"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import revocation
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.redis import get_redis
from app.core.security import AUTH_HEADERS, decode_access_token
from app.crud import module as crud_module
from app.crud import user as crud_user
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.services import audit as audit_service

# Swagger 的 Authorize 按钮走 OAuth2 password flow，需要表单端点；
# 前端业务登录使用 JSON 端点 /auth/login，不依赖此 tokenUrl。
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_PREFIX}/auth/login/form",
    auto_error=False,
)

DbSession = Annotated[AsyncSession, Depends(get_db)]
CacheClient = Annotated[Redis | None, Depends(get_redis)]


async def get_current_user(
    db: DbSession,
    cache: CacheClient,
    token: Annotated[str | None, Depends(oauth2_scheme)] = None,
) -> User:
    """解析 Bearer Token 并加载当前用户。

    校验顺序：签名/过期 → 是否被吊销（jti 黑名单 + 用户级水位）→ 用户是否存在 → 是否停用。
    吊销状态存在 Redis；Redis 不可用时放行（可用性优先），代价是故障期间吊销失效。

    注意：鉴权与业务接口共享同一个 AsyncSession（FastAPI 依赖缓存），
    service 层显式 commit/rollback 时会把这次鉴权读操作一并提交，语义上无副作用。
    """
    if not token:
        raise AppError("NOT_AUTHENTICATED", "请先登录", 401, headers=AUTH_HEADERS)

    payload = decode_access_token(token)
    if await revocation.is_revoked(cache, payload):
        raise AppError("TOKEN_REVOKED", "登录状态已失效，请重新登录", 401, headers=AUTH_HEADERS)

    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AppError("INVALID_TOKEN", "无效的登录凭证", 401, headers=AUTH_HEADERS) from exc

    user = await crud_user.get_by_id(db, user_id)
    if user is None:
        raise AppError("USER_NOT_FOUND", "用户不存在", 401, headers=AUTH_HEADERS)
    if not user.is_active:
        raise AppError("USER_DISABLED", "账号已停用，请联系管理员", 403)
    return user


async def get_current_boss(
    request: Request,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """仅管理员可访问（用于看板、主数据写操作）。拒绝时留下审计。"""
    if user.role != UserRole.BOSS.value:
        await audit_service.record(
            db,
            user=user,
            action="authz.denied",
            module="security",
            status_code=403,
            success=False,
            error_code="FORBIDDEN",
            method=request.method,
            path=request.url.path,
            detail={
                "required_role": UserRole.BOSS.value,
                "actual_role": user.role,
                "path": request.url.path,
            },
            request=request,
            commit=True,
        )
        raise AppError("FORBIDDEN", "仅管理员可访问该接口", 403)
    return user


def require_any_module(codes: list[str]):
    """返回一个校验当前用户是否拥有任一功能模块的依赖。管理员直接放行。"""

    async def _checker(
        request: Request,
        db: DbSession,
        user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if user.role == UserRole.BOSS.value:
            return user
        for code in codes:
            if await crud_module.user_has_module(db, user.id, code):
                return user
        await audit_service.record(
            db,
            user=user,
            action="authz.denied",
            module="security",
            status_code=403,
            success=False,
            error_code="MODULE_FORBIDDEN",
            method=request.method,
            path=request.url.path,
            detail={"required_modules": codes, "actual_role": user.role, "path": request.url.path},
            request=request,
            commit=True,
        )
        raise AppError("FORBIDDEN", "当前账号没有该功能模块权限", 403)

    return _checker


def require_module(code: str):
    """返回一个校验当前用户是否拥有指定功能模块的依赖。管理员直接放行。"""

    async def _checker(
        request: Request,
        db: DbSession,
        user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if user.role == UserRole.BOSS.value:
            return user
        if await crud_module.user_has_module(db, user.id, code):
            return user
        await audit_service.record(
            db,
            user=user,
            action="authz.denied",
            module="security",
            status_code=403,
            success=False,
            error_code="MODULE_FORBIDDEN",
            method=request.method,
            path=request.url.path,
            detail={"required_module": code, "actual_role": user.role, "path": request.url.path},
            request=request,
            commit=True,
        )
        raise AppError("FORBIDDEN", "当前账号没有该功能模块权限", 403)

    return _checker


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentBoss = Annotated[User, Depends(get_current_boss)]
# 原始 Bearer Token 字符串，登出时用来取 jti 做单张吊销
BearerToken = Annotated[str | None, Depends(oauth2_scheme)]
