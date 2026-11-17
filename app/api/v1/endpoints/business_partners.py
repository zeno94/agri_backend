"""供应商 / 客户选项接口。

现有 Vue 前端的采购页调用 /suppliers、销售页调用 /customers；
后端规范模型是统一的 Partner + type，因此这里提供按类型过滤的兼容入口。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.models.enums import PartnerType
from app.schemas.common import Page
from app.schemas.partner import PartnerOut
from app.services import partner as partner_service

router = APIRouter(tags=["往来单位"])


async def _list_by_type(
    db: DbSession,
    *,
    partner_type: str,
    page: int,
    page_size: int,
) -> Page[PartnerOut]:
    return await partner_service.list_partners(
        db,
        page=page,
        size=page_size,
        partner_type=partner_type,
    )


@router.get(
    "/suppliers",
    response_model=Page[PartnerOut],
    summary="供应商列表（前端下拉兼容）",
    description="等价于 GET /partners?partner_type=supplier，默认返回最多 1000 条，供采购页下拉使用。",
)
async def list_suppliers(
    db: DbSession,
    _current_user: CurrentUser,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=1000, description="每页数量")] = 1000,
) -> Page[PartnerOut]:
    return await _list_by_type(
        db,
        partner_type=PartnerType.SUPPLIER.value,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/customers",
    response_model=Page[PartnerOut],
    summary="客户列表（前端下拉兼容）",
    description="等价于 GET /partners?partner_type=customer，默认返回最多 1000 条，供销售页下拉使用。",
)
async def list_customers(
    db: DbSession,
    _current_user: CurrentUser,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=1000, description="每页数量")] = 1000,
) -> Page[PartnerOut]:
    return await _list_by_type(
        db,
        partner_type=PartnerType.CUSTOMER.value,
        page=page,
        page_size=page_size,
    )
