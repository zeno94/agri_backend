"""认证服务：登录校验与 JWT 签发。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.security import (
    AUTH_HEADERS,
    DUMMY_PASSWORD_HASH,
    create_access_token,
    verify_password_async,
)
from app.crud import user as crud_user
from app.schemas.auth import TokenOut
from app.schemas.user import UserOut

INVALID_CREDENTIALS_MESSAGE = "用户名或密码错误"


async def login(db: AsyncSession, username: str, password: str) -> TokenOut:
    """账号密码登录。

    安全细节：
    - 用户不存在时仍执行一次 bcrypt 校验，避免通过响应时间枚举账号；
    - 错误信息统一为「用户名或密码错误」，不区分账号是否存在。
    """
    username = username.strip()
    if not username or not password:
        raise AppError("INVALID_CREDENTIALS", INVALID_CREDENTIALS_MESSAGE, 401, headers=AUTH_HEADERS)

    user = await crud_user.get_by_username(db, username)
    if user is None:
        await verify_password_async(password, DUMMY_PASSWORD_HASH)
        raise AppError("INVALID_CREDENTIALS", INVALID_CREDENTIALS_MESSAGE, 401, headers=AUTH_HEADERS)

    if not await verify_password_async(password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS", INVALID_CREDENTIALS_MESSAGE, 401, headers=AUTH_HEADERS)

    if not user.is_active:
        raise AppError("USER_DISABLED", "账号已停用，请联系管理员", 403)

    token, expires_in = create_access_token(subject=user.id, username=user.username, role=user.role)
    return TokenOut(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
        user=UserOut.model_validate(user),
    )
