"""客户管理接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status

from app.api.deps import CurrentUser, DbSession, require_module
from app.schemas.common import Page
from app.schemas.customer import (
    CustomerCreate,
    CustomerDetailOut,
    CustomerOptionOut,
    CustomerOut,
    CustomerUpdate,
    FollowupCreate,
    FollowupOut,
)
from app.services import audit as audit_service
from app.services import customer as customer_service

router = APIRouter(prefix="/customers", tags=["客户管理"])


@router.get("/options", response_model=Page[CustomerOptionOut], summary="客户下拉选项")
async def customer_options(db: DbSession, _current_user: CurrentUser) -> Page[CustomerOptionOut]:
    items = await customer_service.list_options(db)
    return Page[CustomerOptionOut](
        items=items, total=len(items), page=1, size=max(len(items), 1), pages=1 if items else 0
    )


@router.get(
    "",
    response_model=Page[CustomerOut],
    summary="客户分页查询",
    dependencies=[Depends(require_module("customers"))],
)
async def list_customers(
    db: DbSession,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    keyword: Annotated[str | None, Query(max_length=100, description="姓名/电话")] = None,
    town: Annotated[str | None, Query(max_length=50)] = None,
    customer_type: Annotated[str | None, Query(max_length=30)] = None,
) -> Page[CustomerOut]:
    return await customer_service.list_customers(
        db, page=page, size=size, keyword=keyword, town=town, customer_type=customer_type
    )


@router.get(
    "/{customer_id}",
    response_model=CustomerDetailOut,
    summary="客户详情（含消费统计、跟进、最近订单）",
    dependencies=[Depends(require_module("customers"))],
)
async def get_customer(db: DbSession, customer_id: int) -> CustomerDetailOut:
    return await customer_service.get_detail(db, customer_id)


@router.post(
    "",
    response_model=CustomerOut,
    status_code=status.HTTP_201_CREATED,
    summary="新增客户",
    dependencies=[Depends(require_module("customers"))],
)
async def create_customer(
    payload: CustomerCreate, request: Request, db: DbSession, current_user: CurrentUser
) -> CustomerOut:
    result = await customer_service.create_customer(db, payload)
    await audit_service.record(
        db,
        user=current_user,
        action="customer.create",
        module="customers",
        resource_type="customer",
        resource_id=result.id,
        method="POST",
        path=request.url.path,
        detail={"name": result.name, "phone": result.phone, "town": result.town},
        request=request,
    )
    return result


@router.patch(
    "/{customer_id}",
    response_model=CustomerOut,
    summary="修改客户档案",
    dependencies=[Depends(require_module("customers"))],
)
async def update_customer(
    customer_id: int, payload: CustomerUpdate, request: Request, db: DbSession, current_user: CurrentUser
) -> CustomerOut:
    result = await customer_service.update_customer(db, customer_id, payload)
    await audit_service.record(
        db,
        user=current_user,
        action="customer.update",
        module="customers",
        resource_type="customer",
        resource_id=customer_id,
        method="PATCH",
        path=request.url.path,
        detail=payload.model_dump(exclude_unset=True),
        request=request,
    )
    return result


@router.post(
    "/{customer_id}/followups",
    response_model=FollowupOut,
    status_code=status.HTTP_201_CREATED,
    summary="新增客户跟进",
    dependencies=[Depends(require_module("customers"))],
)
async def create_followup(
    customer_id: int,
    payload: FollowupCreate,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
) -> FollowupOut:
    result = await customer_service.add_followup(db, customer_id=customer_id, payload=payload, operator=current_user)
    await audit_service.record(
        db,
        user=current_user,
        action="customer.followup",
        module="customers",
        resource_type="customer",
        resource_id=customer_id,
        method="POST",
        path=request.url.path,
        detail={"method": result.method, "content": result.content},
        request=request,
    )
    return result
