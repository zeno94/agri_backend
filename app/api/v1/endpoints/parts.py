"""配件管理接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.deps import (
    CacheClient,
    CurrentBoss,
    CurrentUser,
    DbSession,
    require_any_module,
    require_module,
)
from app.schemas.common import Page
from app.schemas.part import PartCreate, PartOut, PartUpdate, PartWarningOut
from app.services import audit as audit_service
from app.services import part as part_service

router = APIRouter(prefix="/parts", tags=["配件管理"])


@router.get(
    "",
    response_model=Page[PartOut],
    summary="配件分页查询（支持名称模糊搜索、分类筛选）",
    dependencies=[Depends(require_module("parts"))],
    description=("先查 Redis 缓存，未命中再查 MySQL 并将结果缓存 5 分钟。" "任何配件资料/库存变更都会使旧缓存失效。"),
)
async def list_parts(
    db: DbSession,
    cache: CacheClient,
    _current_user: CurrentUser,
    page: Annotated[int, Query(ge=1, le=10_000, description="页码，从 1 开始")] = 1,
    size: Annotated[int, Query(ge=1, le=100, description="每页数量，最大 100")] = 20,
    page_size: Annotated[int | None, Query(ge=1, le=1000, description="兼容前端的每页数量，存在时优先于 size")] = None,
    name: Annotated[str | None, Query(max_length=50, description="配件名称模糊搜索")] = None,
    category: Annotated[str | None, Query(max_length=50, description="配件分类精确筛选")] = None,
) -> Page[PartOut]:
    effective_size = page_size or size
    return await part_service.list_parts(db, cache, page=page, size=effective_size, name=name, category=category)


# 注意：静态路径必须声明在 /{part_id} 之前，否则会被动态路由吞掉
@router.get(
    "/warning",
    response_model=list[PartWarningOut],
    summary="库存预警（stock <= safe_stock）",
    dependencies=[Depends(require_any_module(["parts", "warning"]))],
    description="返回所有库存低于等于安全库存的配件，缺货最严重的排在最前。",
)
async def list_warning_parts(db: DbSession, _current_user: CurrentUser) -> list[PartWarningOut]:
    return await part_service.list_warning_parts(db)


@router.get(
    "/{part_id}",
    response_model=PartOut,
    summary="配件详情",
    dependencies=[Depends(require_module("parts"))],
)
async def get_part(part_id: int, db: DbSession, _current_user: CurrentUser) -> PartOut:
    return await part_service.get_part(db, part_id)


@router.post(
    "",
    response_model=PartOut,
    status_code=status.HTTP_201_CREATED,
    summary="新增配件（仅 boss）",
    description="仅管理员可新增配件；初始库存大于 0 时自动生成期初盘点流水。",
)
async def create_part(
    payload: PartCreate,
    request: Request,
    db: DbSession,
    cache: CacheClient,
    current_boss: CurrentBoss,
) -> PartOut:
    result = await part_service.create_part(db, cache, payload, current_boss)
    await audit_service.record(
        db,
        user=current_boss,
        action="part.create",
        module="parts",
        resource_type="part",
        resource_id=result.id,
        method="POST",
        path=request.url.path,
        detail={
            "name": result.name,
            "model": result.model,
            "brand": result.brand,
            "category": result.category,
            "stock": result.stock,
            "purchase_price": result.purchase_price,
            "sale_price": result.sale_price,
        },
        request=request,
    )
    return result


@router.put("/{part_id}", response_model=PartOut, summary="修改配件（仅 boss）")
async def update_part(
    part_id: int,
    payload: PartUpdate,
    request: Request,
    db: DbSession,
    cache: CacheClient,
    current_boss: CurrentBoss,
) -> PartOut:
    result = await part_service.update_part(db, cache, part_id, payload, current_boss)
    await audit_service.record(
        db,
        user=current_boss,
        action="part.update",
        module="parts",
        resource_type="part",
        resource_id=part_id,
        method="PUT",
        path=request.url.path,
        detail={"changed": payload.model_dump(exclude_unset=True), "name": result.name},
        request=request,
    )
    return result
