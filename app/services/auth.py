"""认证服务：登录校验、JWT 签发与登录审计。"""

from __future__ import annotations

from fastapi import Request
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
from app.services import audit as audit_service
from app.services import user as user_service

INVALID_CREDENTIALS_MESSAGE = "用户名或密码错误"


async def _record_login_failure(
    db: AsyncSession,
    *,
    username: str,
    reason: str,
    status_code: int,
    error_code: str,
    user=None,
    request: Request | None = None,
) -> None:
    await audit_service.record(
        db,
        user=user,
        username=username,
        action="auth.login_failed",
        module="auth",
        status_code=status_code,
        success=False,
        error_code=error_code,
        detail={"username": username, "reason": reason},
        request=request,
        commit=True,
    )


async def login(
    db: AsyncSession,
    username: str,
    password: str,
    request: Request | None = None,
) -> TokenOut:
    """账号密码登录。

    安全细节：
    - 用户不存在时仍执行一次 bcrypt 校验，避免通过响应时间枚举账号；
    - 错误信息统一为「用户名或密码错误」，不区分账号是否存在；
    - 审计日志只记录账号与失败原因，绝不记录密码。
    """
    username = username.strip()
    if not username or not password:
        await _record_login_failure(
            db,
            username=username,
            reason="empty_credentials",
            status_code=401,
            error_code="INVALID_CREDENTIALS",
            request=request,
        )
        raise AppError("INVALID_CREDENTIALS", INVALID_CREDENTIALS_MESSAGE, 401, headers=AUTH_HEADERS)

    user = await crud_user.get_by_username(db, username)
    if user is None:
        await verify_password_async(password, DUMMY_PASSWORD_HASH)
        await _record_login_failure(
            db,
            username=username,
            reason="user_not_found",
            status_code=401,
            error_code="INVALID_CREDENTIALS",
            request=request,
        )
        raise AppError("INVALID_CREDENTIALS", INVALID_CREDENTIALS_MESSAGE, 401, headers=AUTH_HEADERS)

    if not await verify_password_async(password, user.password_hash):
        await _record_login_failure(
            db,
            username=username,
            reason="invalid_credentials",
            status_code=401,
            error_code="INVALID_CREDENTIALS",
            user=user,
            request=request,
        )
        raise AppError("INVALID_CREDENTIALS", INVALID_CREDENTIALS_MESSAGE, 401, headers=AUTH_HEADERS)

    if not user.is_active:
        await _record_login_failure(
            db,
            username=username,
            reason="user_disabled",
            status_code=403,
            error_code="USER_DISABLED",
            user=user,
            request=request,
        )
        raise AppError("USER_DISABLED", "账号已停用，请联系管理员", 403)

    token, expires_in = create_access_token(subject=user.id, username=user.username, role=user.role)
    await audit_service.record(
        db,
        user=user,
        action="auth.login",
        module="auth",
        status_code=200,
        success=True,
        detail={"username": user.username, "role": user.role, "result": "success"},
        request=request,
        commit=True,
    )
    return TokenOut(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
        user=await user_service.get_profile(db, user),
    )
