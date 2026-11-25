"""供应商管理接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request, status

from app.api.deps import CurrentBoss, CurrentUser, DbSession
from app.schemas.common import Page
from app.schemas.supplier import (
    SupplierCreate,
    SupplierListItem,
    SupplierOptionOut,
    SupplierOut,
    SupplierUpdate,
)
from app.services import audit as audit_service
from app.services import supplier as supplier_service

router = APIRouter(prefix="/suppliers", tags=["供应商管理"])


@router.get("/options", response_model=Page[SupplierOptionOut], summary="供应商下拉选项")
async def supplier_options(db: DbSession, _current_user: CurrentUser) -> Page[SupplierOptionOut]:
    items = await supplier_service.list_options(db)
    return Page[SupplierOptionOut](
        items=items, total=len(items), page=1, size=max(len(items), 1), pages=1 if items else 0
    )


@router.get("", response_model=Page[SupplierListItem], summary="供应商分页查询")
async def list_suppliers(
    db: DbSession,
    _current_boss: CurrentBoss,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    keyword: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[SupplierListItem]:
    return await supplier_service.list_suppliers(db, page=page, size=size, keyword=keyword)


@router.post(
    "",
    response_model=SupplierOut,
    status_code=status.HTTP_201_CREATED,
    summary="新增供应商",
)
async def create_supplier(
    payload: SupplierCreate, request: Request, db: DbSession, current_boss: CurrentBoss
) -> SupplierOut:
    result = await supplier_service.create_supplier(db, payload)
    await audit_service.record(
        db,
        user=current_boss,
        action="supplier.create",
        module="suppliers",
        resource_type="supplier",
        resource_id=result.id,
        method="POST",
        path=request.url.path,
        detail={"name": result.name, "phone": result.phone},
        request=request,
    )
    return result


@router.patch("/{supplier_id}", response_model=SupplierOut, summary="修改供应商")
async def update_supplier(
    supplier_id: int,
    payload: SupplierUpdate,
    request: Request,
    db: DbSession,
    current_boss: CurrentBoss,
) -> SupplierOut:
    result = await supplier_service.update_supplier(db, supplier_id, payload)
    await audit_service.record(
        db,
        user=current_boss,
        action="supplier.update",
        module="suppliers",
        resource_type="supplier",
        resource_id=supplier_id,
        method="PATCH",
        path=request.url.path,
        detail=payload.model_dump(exclude_unset=True),
        request=request,
    )
    return result
