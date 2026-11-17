"""容器启动前等待数据库可用，避免应用在 MySQL 就绪前崩溃。"""

from __future__ import annotations

import asyncio

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings


async def wait_for_database(max_attempts: int = 60, delay: float = 2.0) -> None:
    if make_url(settings.DATABASE_URL).get_backend_name() == "sqlite":
        print("[wait_for_db] SQLite 模式，跳过等待", flush=True)
        return

    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            print(f"[wait_for_db] 数据库已就绪（第 {attempt} 次尝试）", flush=True)
            return
        except Exception as exc:  # noqa: BLE001 - 启动阶段需要捕获所有连接异常
            last_error = exc
            print(f"[wait_for_db] 等待中（{attempt}/{max_attempts}）：{exc}", flush=True)
            await asyncio.sleep(delay)
        finally:
            await engine.dispose()

    raise SystemExit(f"[wait_for_db] 数据库在预期时间内不可用：{last_error}")


if __name__ == "__main__":
    asyncio.run(wait_for_database())
