"""FastAPI 应用入口。

启动流程（lifespan）：
1. 等待 MySQL 可用（容器编排下数据库可能晚于应用启动）；
2. 连接 Redis（失败自动降级，不影响核心交易）；
3. 可选自动建表（仅本地开发，生产由 Alembic 管理）；
4. 关闭时释放 Redis 与数据库连接池。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import app.models  # noqa: F401  # 确保所有 ORM 模型完成注册（create_all / Alembic 需要）
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.core.middleware import RequestContextMiddleware
from app.core.redis import redis_manager
from app.db.base import Base
from app.db.session import check_database, dispose_engine, engine, wait_for_database

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("正在启动 %s v%s（环境：%s）", settings.APP_NAME, settings.APP_VERSION, settings.ENVIRONMENT)

    await wait_for_database()
    await redis_manager.connect()

    if settings.AUTO_CREATE_TABLES:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.warning("AUTO_CREATE_TABLES=true：已按模型自动建表，生产环境请改用 Alembic")

    logger.info("应用启动完成，接口文档：/docs")
    yield

    await redis_manager.close()
    await dispose_engine()
    logger.info("应用已关闭")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "FastAPI + SQLAlchemy 2.0 + MySQL 8.0 + Redis + JWT 实现的农机配件进销存后端。\n\n"
        "**鉴权方式**：调用 `/api/v1/auth/login` 获取 JWT，点击右上角 Authorize 填入即可调试。\n\n"
        "**错误格式**：`{\"code\": \"业务错误码\", \"message\": \"提示\", \"detail\": {...}}`"
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    contact={"name": "ERP 后端团队"},
    license_info={"name": "Proprietary"},
)

# CORS：默认允许所有来源，便于 Vue 前端跨域联调。
# 使用 Bearer Token 而非 Cookie，因此 allow_credentials 必须为 False（与 "*" 搭配的浏览器规范要求）。
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
    max_age=600,
)
app.add_middleware(RequestContextMiddleware)

register_exception_handlers(app)
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health", tags=["系统"], summary="存活探针")
async def health() -> dict[str, str]:
    return {"status": "ok", "timestamp": datetime.now(UTC).isoformat(timespec="seconds")}


@app.get("/ready", tags=["系统"], summary="就绪探针（数据库 + Redis）")
async def ready() -> JSONResponse:
    database_ok = await check_database()
    redis_ok = await redis_manager.ping()
    # Redis 不可用时应用仍可降级服务，因此只有数据库故障才判定为未就绪
    return JSONResponse(
        status_code=200 if database_ok else 503,
        content={
            "status": "ok" if database_ok else "unavailable",
            "database": database_ok,
            "redis": redis_ok,
        },
    )


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
