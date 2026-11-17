"""配件服务：列表缓存、资料维护、库存预警。

缓存策略（Cache-Aside）：
1. 先读 Redis，命中直接返回；
2. 未命中查 MySQL，结果序列化 JSON 写回 Redis，TTL 5 分钟；
3. 任何写操作（新增/修改/采购/销售）都会通过版本号自增让旧缓存失效。
"""

from __future__ import annotations

from pydantic import ValidationError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import (
    build_parts_cache_key,
    cache_get_text,
    cache_set_text,
    get_cache_version,
    invalidate_parts_cache,
)
from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.crud import part as crud_part
from app.models.enums import ChangeType
from app.models.inventory_log import InventoryLog
from app.models.user import User
from app.schemas.common import Page
from app.schemas.part import PartCreate, PartOut, PartUpdate, PartWarningOut
from app.services.common import calc_pages

logger = get_logger(__name__)


async def list_parts(
    db: AsyncSession,
    redis: Redis | None,
    *,
    page: int,
    size: int,
    name: str | None = None,
    category: str | None = None,
) -> Page[PartOut]:
    name = name.strip() if name else None
    category = category.strip() if category else None

    cache_key: str | None = None
    if redis is not None:
        version = await get_cache_version(redis)
        cache_key = build_parts_cache_key(version, page=page, size=size, name=name, category=category)
        cached = await cache_get_text(redis, cache_key)
        if cached:
            try:
                return Page[PartOut].model_validate_json(cached)
            except ValidationError:
                logger.warning("配件列表缓存反序列化失败，回源数据库：%s", cache_key)

    rows, total = await crud_part.list_parts(db, page=page, size=size, name=name, category=category)
    result = Page[PartOut](
        items=[PartOut.model_validate(part) for part in rows],
        total=total,
        page=page,
        size=size,
        pages=calc_pages(total, size),
    )

    if cache_key is not None:
        await cache_set_text(redis, cache_key, result.model_dump_json())
    return result


async def get_part(db: AsyncSession, part_id: int) -> PartOut:
    part = await crud_part.get_by_id(db, part_id)
    if part is None:
        raise AppError("PART_NOT_FOUND", "配件不存在", 404)
    return PartOut.model_validate(part)


async def create_part(
    db: AsyncSession,
    redis: Redis | None,
    payload: PartCreate,
    operator: User,
) -> PartOut:
    """新增配件。初始库存 > 0 时写入期初盘点流水，保证库存来源可追溯。"""
    try:
        part = await crud_part.create_part(db, payload.model_dump())
        if part.stock > 0:
            db.add(
                InventoryLog(
                    part_id=part.id,
                    change_type=ChangeType.CHECK.value,
                    change_qty=part.stock,
                    before_stock=0,
                    after_stock=part.stock,
                    operator_id=operator.id,
                    remark="新增配件-期初库存",
                )
            )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    await db.refresh(part)
    await invalidate_parts_cache(redis)
    return PartOut.model_validate(part)


async def update_part(
    db: AsyncSession,
    redis: Redis | None,
    part_id: int,
    payload: PartUpdate,
    operator: User,
) -> PartOut:
    """修改配件资料。

    stock 属于敏感字段：只允许通过本接口调整，且每次变化都会生成 check 类型的
    库存流水，避免出现「库存凭空变化」的黑账。
    """
    part = await crud_part.get_by_id(db, part_id)
    if part is None:
        raise AppError("PART_NOT_FOUND", "配件不存在", 404)

    values = payload.model_dump(exclude_unset=True)
    new_stock = values.pop("stock", None)

    try:
        if new_stock is not None and new_stock != part.stock:
            before_stock = part.stock
            part.stock = new_stock
            db.add(
                InventoryLog(
                    part_id=part.id,
                    change_type=ChangeType.CHECK.value,
                    change_qty=new_stock - before_stock,
                    before_stock=before_stock,
                    after_stock=new_stock,
                    operator_id=operator.id,
                    remark=f"库存盘点调整（{before_stock} -> {new_stock}）",
                )
            )
        if values:
            await crud_part.apply_update(db, part, values)
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    await db.refresh(part)
    await invalidate_parts_cache(redis)
    return PartOut.model_validate(part)


async def list_warning_parts(db: AsyncSession) -> list[PartWarningOut]:
    parts = await crud_part.list_warning_parts(db)
    result: list[PartWarningOut] = []
    for part in parts:
        data = PartOut.model_validate(part).model_dump()
        data["shortage"] = max(part.safe_stock - part.stock, 0)
        result.append(PartWarningOut(**data))
    return result
