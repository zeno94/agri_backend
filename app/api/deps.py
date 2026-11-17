"""API 依赖：数据库会话、Redis、当前用户与角色校验。"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.redis import get_redis
from app.core.security import AUTH_HEADERS, decode_access_token
from app.crud import user as crud_user
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.user import User

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
    token: Annotated[str | None, Depends(oauth2_scheme)] = None,
) -> User:
    """解析 Bearer Token 并加载当前用户。

    注意：鉴权与业务接口共享同一个 AsyncSession（FastAPI 依赖缓存），
    service 层显式 commit/rollback 时会把这次鉴权读操作一并提交，语义上无副作用。
    """
    if not token:
        raise AppError("NOT_AUTHENTICATED", "请先登录", 401, headers=AUTH_HEADERS)

    payload = decode_access_token(token)
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


async def get_current_boss(user: Annotated[User, Depends(get_current_user)]) -> User:
    """仅老板可访问（用于看板等经营数据接口）。"""
    if user.role != UserRole.BOSS.value:
        raise AppError("FORBIDDEN", "仅老板可访问该接口", 403)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentBoss = Annotated[User, Depends(get_current_boss)]
