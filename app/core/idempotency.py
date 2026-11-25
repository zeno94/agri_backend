"""幂等键：同一请求重复提交只执行一次。

为什么需要
----------
前端有「提交中」状态，能挡住手抖双击；但挡不住超时重试、刷新重填、多标签页、网关自动重发。
这些场景下服务端会收到两个内容完全相同的请求，如果没有唯一标识，就会产生两张单、扣两次库存。

键设计
------
    erp:idem:{scope}:{client_key}

- `client_key` 由客户端生成（UUID），一次业务尝试一个，重试时复用；
- `scope` 区分业务，避免销售单的 key 和采购单的 key 撞车。

流程
----
1. `SET key pending NX EX ttl` 抢占：
   - 抢到 → 首次执行；
   - 没抢到 → 读值：
     - `pending` → 上一次还在处理，返回 409，让客户端稍等；
     - 其他 → 已完成，直接回放上次的状态码与响应体（带 `Idempotent-Replay: true`）。
2. 执行成功 → 把 `{status, body}` 存回键；
3. 执行失败 → 删除键，允许客户端用同一个 key 重试。

降级
----
Redis 不可用时不阻断业务：`acquire` 返回 None，请求按普通流程执行（与缓存一致，
缓存是加速器不是单点依赖）。代价是 Redis 故障期间幂等失效，这一点在 README 里明说。
"""

from __future__ import annotations

import json
import re
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.responses import JSONResponse

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import get_logger

logger = get_logger(__name__)

# 客户端生成的键：8~64 位，只允许字母数字与 - _
CLIENT_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
PENDING = "__pending__"


def _key(scope: str, client_key: str) -> str:
    return f"{settings.IDEMPOTENCY_PREFIX}:{scope}:{client_key}"


async def acquire(redis: Redis | None, scope: str, client_key: str | None) -> str | None:
    """占用幂等键。

    返回 None 表示「首次执行，请继续处理」；
    返回非空字符串表示「命中历史结果」，内容是 JSON `{"status": int, "body": ...}`。
    """
    if redis is None or not client_key:
        return None

    if not CLIENT_KEY_PATTERN.match(client_key):
        raise AppError(
            "INVALID_IDEMPOTENCY_KEY",
            "Idempotency-Key 格式不合法：需 8~64 位字母、数字、下划线或短横线",
            400,
        )

    redis_key = _key(scope, client_key)
    try:
        created = await redis.set(redis_key, PENDING, nx=True, ex=settings.IDEMPOTENCY_TTL_SECONDS)
    except RedisError as exc:
        logger.warning("幂等键抢占失败，降级为不去重：%s", exc)
        return None

    if created:
        return None

    try:
        value = await redis.get(redis_key)
    except RedisError as exc:
        logger.warning("幂等结果读取失败，降级为不去重：%s", exc)
        return None

    if value and value != PENDING:
        logger.info("命中幂等键，回放首次结果：scope=%s", scope)
        return value

    # 键存在但仍是 pending：同一笔请求还在处理中
    raise AppError("REQUEST_IN_PROGRESS", "相同请求正在处理中，请勿重复提交", 409)


async def store(redis: Redis | None, scope: str, client_key: str | None, status_code: int, body: Any) -> None:
    """把成功结果写回幂等键，供后续重复请求回放。"""
    if redis is None or not client_key:
        return
    try:
        await redis.set(
            _key(scope, client_key),
            json.dumps({"status": status_code, "body": body}, ensure_ascii=False, default=str),
            ex=settings.IDEMPOTENCY_TTL_SECONDS,
        )
    except (RedisError, TypeError, ValueError) as exc:
        logger.warning("幂等结果写入失败，重复请求将重新执行：%s", exc)


async def release(redis: Redis | None, scope: str, client_key: str | None) -> None:
    """执行失败时释放键，让客户端可以用同一个 key 安全重试。"""
    if redis is None or not client_key:
        return
    try:
        await redis.delete(_key(scope, client_key))
    except RedisError as exc:
        logger.warning("幂等键释放失败，最多 TTL 后自动过期：%s", exc)


def replay_response(cached: str) -> JSONResponse:
    """把首次执行的结果原样回放给重复请求。

    响应头带 `Idempotent-Replay: true`，客户端和排障时能一眼看出这是回放而非新执行。
    """
    data = json.loads(cached)
    return JSONResponse(
        status_code=int(data.get("status", 200)),
        content=data.get("body"),
        headers={"Idempotent-Replay": "true"},
    )
