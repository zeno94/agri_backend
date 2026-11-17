"""安全组件：密码哈希与 JWT 签发/校验。

密码策略：先对明文做 SHA-256 再 Base64，然后交给 bcrypt。
这样可以避开 bcrypt 72 字节截断问题，又保留 bcrypt 的慢哈希特性。
"""

from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import bcrypt
import jwt
from fastapi.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import get_logger

logger = get_logger(__name__)

AUTH_HEADERS = {"WWW-Authenticate": "Bearer"}


def _prehash(password: str) -> bytes:
    """将任意长度密码压缩为固定长度的 bcrypt 输入。"""
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(_prehash(plain_password), password_hash.encode("utf-8"))
    except (ValueError, TypeError):  # 损坏的哈希不应导致 500
        return False


async def hash_password_async(password: str) -> str:
    """bcrypt 是 CPU 密集型操作，放在线程池执行避免阻塞事件循环。"""
    return await run_in_threadpool(hash_password, password)


async def verify_password_async(plain_password: str, password_hash: str) -> bool:
    return await run_in_threadpool(verify_password, plain_password, password_hash)


# 用户不存在时也执行一次 bcrypt 校验，抹平响应时间差异，防止用户名枚举
DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing-attack-mitigation")


def create_access_token(*, subject: int | str, username: str, role: str) -> tuple[str, int]:
    """签发 JWT，返回 (token, 有效期秒数)。"""
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "username": username,
        "role": role,
        "type": "access",
        "iat": now,
        "nbf": now,
        "exp": expires_at,
        "jti": uuid4().hex,
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


def decode_access_token(token: str) -> dict[str, Any]:
    """解析并校验 JWT；任何非法情况统一转换为 401。"""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AppError("TOKEN_EXPIRED", "登录已过期，请重新登录", 401, headers=AUTH_HEADERS) from exc
    except jwt.InvalidTokenError as exc:
        logger.info("JWT 校验失败：%s", exc)
        raise AppError("INVALID_TOKEN", "无效的登录凭证", 401, headers=AUTH_HEADERS) from exc

    if payload.get("type") != "access":
        raise AppError("INVALID_TOKEN", "无效的登录凭证类型", 401, headers=AUTH_HEADERS)
    return payload
