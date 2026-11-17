"""Redis 异步客户端管理。

设计原则：缓存是「加速器」而不是「单点依赖」。
Redis 不可用时应用自动降级为直连数据库，仅记录告警，不影响核心交易。
"""

from __future__ import annotations

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class RedisManager:
    def __init__(self) -> None:
        self._client: Redis | None = None

    @property
    def client(self) -> Redis | None:
        return self._client

    @property
    def available(self) -> bool:
        return self._client is not None

    async def connect(self) -> None:
        client = Redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            socket_connect_timeout=settings.REDIS_SOCKET_TIMEOUT,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
            health_check_interval=30,
        )
        try:
            await client.ping()
        except RedisError as exc:
            await client.aclose()
            self._client = None
            logger.warning("Redis 连接失败，列表缓存降级为直连数据库：%s", exc)
            return
        self._client = client
        logger.info("Redis 连接成功：%s", settings.REDIS_URL)

    async def ping(self) -> bool:
        if self._client is None:
            return False
        try:
            return bool(await self._client.ping())
        except RedisError:
            return False

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.info("Redis 连接已关闭")


redis_manager = RedisManager()


async def get_redis() -> Redis | None:
    """FastAPI 依赖：返回全局 Redis 客户端，可能为 None（降级模式）。"""
    return redis_manager.client
