"""JWT 吊销：让已经签发出去的 Token 提前失效。

为什么需要
----------
JWT 是「自证」的：服务端不保存会话，每次请求只验签名和过期时间，所以签发之后
无法撤回。它像一张盖了章、写明有效期的通行证，发出去就得认到过期。

要支持吊销，必须引入一点服务端状态。这里用两层，分别覆盖两类场景：

1. 单张 Token 作废 —— 登出、Token 泄露、设备丢失
       erp:jwt:deny:{jti} = 1
   TTL 等于这张 Token 的剩余寿命，到期自动清理，不会无限增长。

2. 某个用户的全部 Token 作废 —— 管理员重置密码、停用账号
       erp:jwt:cutoff:{user_id} = 秒级时间戳
   签发时间（iat）早于水位的 Token 全部拒绝。
   水位 TTL = Token 最长寿命 + 60 秒：等所有旧 Token 都自然过期后，水位也没有意义了。

取舍
----
- 成本：每次鉴权多 1~2 次 Redis 查询（`EXISTS` + `GET`，都是 O(1)）；
- 降级：Redis 不可用时 **fail-open**（放行）。理由是可用性优先——缓存/吊销状态丢了
  不应该让整个系统登录不了。代价是 Redis 故障期间吊销失效，这一点要写进文档，不能装作没有。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# 水位多留 60 秒，覆盖时钟漂移与临界边界
_CUTOFF_GRACE_SECONDS = 60


def _deny_key(jti: str) -> str:
    return f"{settings.JWT_REVOCATION_PREFIX}:deny:{jti}"


def _cutoff_key(user_id: int | str) -> str:
    return f"{settings.JWT_REVOCATION_PREFIX}:cutoff:{user_id}"


async def revoke_token(redis: Redis | None, payload: dict[str, Any]) -> bool:
    """吊销单张 Token（登出）。返回是否真的写入了吊销标记。"""
    if redis is None:
        return False

    jti = payload.get("jti")
    exp = payload.get("exp")
    if not jti or not exp:
        # 历史 Token 可能没有 jti，无法做单张吊销，只能靠账号停用兜底
        logger.warning("Token 缺少 jti/exp，跳过单张吊销")
        return False

    ttl = int(exp) - int(datetime.now(UTC).timestamp())
    if ttl <= 0:
        return False  # 已经过期，不需要再记

    try:
        await redis.set(_deny_key(str(jti)), "1", ex=ttl)
    except RedisError as exc:
        logger.warning("写入 Token 吊销标记失败：%s", exc)
        return False
    return True


async def revoke_user_tokens(redis: Redis | None, user_id: int | str) -> bool:
    """吊销某个用户的全部 Token（改密 / 停用）。返回是否写入成功。"""
    if redis is None:
        return False

    now = int(datetime.now(UTC).timestamp())
    ttl = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60 + _CUTOFF_GRACE_SECONDS
    try:
        await redis.set(_cutoff_key(user_id), now, ex=ttl)
    except RedisError as exc:
        logger.warning("写入用户吊销水位失败：%s", exc)
        return False
    logger.info("已吊销用户全部 Token：user_id=%s", user_id)
    return True


async def is_revoked(redis: Redis | None, payload: dict[str, Any]) -> bool:
    """判断当前 Token 是否已被吊销。Redis 不可用时放行（fail-open）。"""
    if redis is None:
        return False

    jti = payload.get("jti")
    if jti:
        try:
            if await redis.exists(_deny_key(str(jti))):
                return True
        except RedisError as exc:
            logger.warning("查询 Token 吊销标记失败，放行：%s", exc)
            return False

    user_id = payload.get("sub")
    issued_at = payload.get("iat")
    if user_id is not None and issued_at is not None:
        try:
            cutoff = await redis.get(_cutoff_key(user_id))
        except RedisError as exc:
            logger.warning("查询用户吊销水位失败，放行：%s", exc)
            return False
        if cutoff is not None:
            try:
                if int(issued_at) < int(cutoff):
                    return True
            except (TypeError, ValueError):
                return False

    return False
