"""往来单位接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession
from app.models.enums import PartnerType
from app.schemas.common import Page
from app.schemas.partner import PartnerCreate, PartnerOut
from app.services import partner as partner_service

router = APIRouter(prefix="/partners", tags=["往来单位"])


@router.get("", response_model=Page[PartnerOut], summary="往来单位分页查询")
async def list_partners(
    db: DbSession,
    _current_user: CurrentUser,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    partner_type: Annotated[PartnerType | None, Query(description="supplier / customer")] = None,
    name: Annotated[str | None, Query(max_length=100, description="单位名称模糊搜索")] = None,
) -> Page[PartnerOut]:
    return await partner_service.list_partners(
        db,
        page=page,
        size=size,
        partner_type=partner_type.value if partner_type else None,
        name=name,
    )


@router.post(
    "",
    response_model=PartnerOut,
    status_code=status.HTTP_201_CREATED,
    summary="新增往来单位",
)
async def create_partner(payload: PartnerCreate, db: DbSession, _current_user: CurrentUser) -> PartnerOut:
    return await partner_service.create_partner(db, payload)
