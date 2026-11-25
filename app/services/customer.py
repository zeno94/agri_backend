"""客户管理服务。"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.money import money
from app.crud import customer as crud_customer
from app.models.customer import Customer, CustomerFollowup
from app.models.user import User
from app.schemas.common import Page
from app.schemas.customer import (
    CustomerCreate,
    CustomerDetailOut,
    CustomerOptionOut,
    CustomerOut,
    CustomerStats,
    CustomerUpdate,
    FollowupCreate,
    FollowupOut,
)
from app.services.common import calc_pages


def _stats(order_count: int, total_amount: Decimal, first_order_at, last_order_at) -> CustomerStats:
    count = int(order_count or 0)
    total = Decimal(str(total_amount or 0))
    return CustomerStats(
        order_count=count,
        total_amount=money(total),
        avg_order_amount=money(total / count) if count else Decimal("0.00"),
        first_order_at=first_order_at,
        last_order_at=last_order_at,
    )


def customer_address(customer: Customer) -> str:
    return "".join(filter(None, [customer.city, customer.county, customer.town, customer.village]))


def customer_display_name(customer: Customer) -> str:
    address = customer_address(customer)
    return f"{customer.name}（{address}）" if address else customer.name


def _out(customer: Customer, stats: CustomerStats) -> CustomerOut:
    return CustomerOut(
        id=customer.id,
        name=customer.name,
        phone=customer.phone,
        city=customer.city,
        county=customer.county,
        town=customer.town,
        village=customer.village,
        customer_type=customer.customer_type,
        acreage=customer.acreage if customer.acreage is not None else Decimal("0.0"),
        main_crops=list(customer.main_crops or []),
        tags=list(customer.tags or []),
        note=customer.note,
        next_follow_up_at=customer.next_follow_up_at,
        is_active=customer.is_active,
        created_at=customer.created_at,
        updated_at=customer.updated_at,
        stats=stats,
    )


def _followup_out(followup: CustomerFollowup) -> FollowupOut:
    return FollowupOut(
        id=followup.id,
        customer_id=followup.customer_id,
        operator_id=followup.operator_id,
        operator_name=followup.operator.username if followup.operator is not None else "",
        method=followup.method,
        content=followup.content,
        next_follow_up_at=followup.next_follow_up_at,
        created_at=followup.created_at,
    )


async def list_customers(
    db: AsyncSession,
    *,
    page: int,
    size: int,
    keyword: str | None = None,
    town: str | None = None,
    customer_type: str | None = None,
) -> Page[CustomerOut]:
    rows, total = await crud_customer.list_customers(
        db,
        page=page,
        size=size,
        keyword=keyword,
        town=town,
        customer_type=customer_type,
    )
    items = [
        _out(customer, _stats(count, amount, first_at, last_at)) for customer, count, amount, first_at, last_at in rows
    ]
    return Page[CustomerOut](
        items=items,
        total=total,
        page=page,
        size=size,
        pages=calc_pages(total, size),
    )


async def list_options(db: AsyncSession) -> list[CustomerOptionOut]:
    return [
        CustomerOptionOut(
            id=c.id,
            name=c.name,
            phone=c.phone,
            city=c.city,
            county=c.county,
            town=c.town,
            village=c.village,
            display_name=customer_display_name(c),
        )
        for c in await crud_customer.options(db)
    ]


async def get_detail(db: AsyncSession, customer_id: int) -> CustomerDetailOut:
    customer = await crud_customer.get_by_id(db, customer_id)
    if customer is None:
        raise AppError("CUSTOMER_NOT_FOUND", "客户不存在", 404)

    count, amount, first_at, last_at = await crud_customer.stats_for_customer(db, customer_id)
    stats = _stats(count, amount, first_at, last_at)

    followups = await crud_customer.list_followups(db, customer_id)
    orders = await crud_customer.recent_orders(db, customer_id)
    base = _out(customer, stats)
    return CustomerDetailOut(
        **base.model_dump(),
        followups=[_followup_out(f) for f in followups],
        recent_orders=[
            {
                "id": order.id,
                "order_no": order.order_no,
                "total_amount": money(order.total_amount),
                "status": order.status,
                "created_at": order.created_at.replace(tzinfo=UTC).isoformat(),
                "item_count": len(order.items),
            }
            for order in orders
        ],
    )


async def create_customer(db: AsyncSession, payload: CustomerCreate) -> CustomerOut:
    customer = await crud_customer.create_customer(db, payload.model_dump())
    await db.commit()
    await db.refresh(customer)
    return _out(customer, CustomerStats())


async def update_customer(db: AsyncSession, customer_id: int, payload: CustomerUpdate) -> CustomerOut:
    customer = await crud_customer.get_by_id(db, customer_id)
    if customer is None:
        raise AppError("CUSTOMER_NOT_FOUND", "客户不存在", 404)
    values = payload.model_dump(exclude_unset=True)
    await crud_customer.update_customer(db, customer, values)
    await db.commit()
    await db.refresh(customer)
    stats = CustomerStats()
    return _out(customer, stats)


async def add_followup(
    db: AsyncSession,
    *,
    customer_id: int,
    payload: FollowupCreate,
    operator: User,
) -> FollowupOut:
    customer = await crud_customer.get_by_id(db, customer_id)
    if customer is None:
        raise AppError("CUSTOMER_NOT_FOUND", "客户不存在", 404)

    followup = await crud_customer.create_followup(
        db,
        {
            "customer_id": customer_id,
            "operator_id": operator.id,
            "method": payload.method,
            "content": payload.content,
            "next_follow_up_at": payload.next_follow_up_at,
            "created_at": datetime.now(UTC).replace(tzinfo=None),
        },
    )
    customer.last_contact_at = datetime.now(UTC).replace(tzinfo=None)
    customer.next_follow_up_at = payload.next_follow_up_at
    await db.commit()
    loaded = await crud_customer.get_followup(db, followup.id)
    assert loaded is not None
    return _followup_out(loaded)
