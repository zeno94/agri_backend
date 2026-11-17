"""异步数据库引擎与会话工厂。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _create_engine() -> AsyncEngine:
    url = settings.DATABASE_URL
    engine_kwargs: dict[str, Any] = {
        "echo": settings.DB_ECHO,
        "pool_pre_ping": True,
    }
    # SQLite 不支持 MySQL 风格的连接池参数（测试环境使用）
    if make_url(url).get_backend_name() != "sqlite":
        engine_kwargs.update(
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_recycle=settings.DB_POOL_RECYCLE,
            pool_timeout=settings.DB_POOL_TIMEOUT,
        )
    return create_async_engine(url, **engine_kwargs)


engine: AsyncEngine = _create_engine()

# expire_on_commit=False：commit 后仍可安全读取 ORM 对象属性，避免异步场景下的隐式 IO
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：每个请求一个 AsyncSession。

    事务由 service 层显式 commit / rollback；这里只负责异常兜底与资源释放。
    """
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def check_database() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError as exc:
        logger.warning("数据库健康检查失败：%s", exc)
        return False


async def wait_for_database(retries: int = 15, delay: float = 2.0) -> None:
    """启动时等待数据库可用（容器编排下 MySQL 可能尚未就绪）。"""
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("数据库连接成功（第 %s 次尝试）", attempt)
            return
        except SQLAlchemyError as exc:
            last_error = exc
            logger.warning("数据库未就绪（%s/%s）：%s", attempt, retries, exc)
            if attempt < retries:
                await asyncio.sleep(delay)
    raise RuntimeError("数据库在预期时间内不可用") from last_error


async def dispose_engine() -> None:
    await engine.dispose()
