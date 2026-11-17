"""配件列表缓存。

键设计：erp:parts:list:v{version}:{fingerprint}
- version 是 Redis 中的自增计数器，任何库存/资料变更都会 INCR，使旧缓存自然失效；
- 旧版本 key 仍保留但无人读取，随 5 分钟 TTL 自动回收，避免在高并发下全量 SCAN 删除；
- Redis 故障时所有操作静默降级，不影响数据库查询。
"""

from __future__ import annotations

import hashlib
import json

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

CACHE_VERSION_KEY = f"{settings.PARTS_CACHE_PREFIX}:cache_version"


def build_parts_cache_key(
    version: int,
    *,
    page: int,
    size: int,
    name: str | None,
    category: str | None,
) -> str:
    """基于查询条件生成短小、可读的缓存键。"""
    fingerprint = hashlib.sha1(
        json.dumps([page, size, name, category], ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]
    return f"{settings.PARTS_CACHE_PREFIX}:list:v{version}:{fingerprint}"


async def get_cache_version(redis: Redis) -> int:
    try:
        raw = await redis.get(CACHE_VERSION_KEY)
        return int(raw) if raw is not None else 0
    except (RedisError, ValueError) as exc:
        logger.warning("读取缓存版本失败，降级处理：%s", exc)
        return 0


async def invalidate_parts_cache(redis: Redis | None) -> None:
    """配件资料或库存变化后调用：版本号自增，立即让存量缓存失效。"""
    if redis is None:
        return
    try:
        await redis.incr(CACHE_VERSION_KEY)
    except RedisError as exc:
        logger.warning("缓存版本自增失败，最多 5 分钟后自然过期：%s", exc)


async def cache_get_text(redis: Redis | None, key: str) -> str | None:
    if redis is None:
        return None
    try:
        return await redis.get(key)
    except RedisError as exc:
        logger.warning("读取缓存失败，回源数据库：%s", exc)
        return None


async def cache_set_text(redis: Redis | None, key: str, value: str, ttl: int | None = None) -> None:
    if redis is None:
        return
    try:
        await redis.set(key, value, ex=ttl or settings.CACHE_TTL_SECONDS)
    except RedisError as exc:
        logger.warning("写入缓存失败，忽略：%s", exc)
