"""供应商管理服务。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.money import money
from app.crud import supplier as crud_supplier
from app.schemas.common import Page
from app.schemas.supplier import (
    SupplierCreate,
    SupplierListItem,
    SupplierOptionOut,
    SupplierOut,
    SupplierUpdate,
)
from app.services.common import calc_pages


def _out(supplier) -> SupplierOut:
    return SupplierOut.model_validate(supplier)


async def list_suppliers(
    db: AsyncSession, *, page: int, size: int, keyword: str | None = None
) -> Page[SupplierListItem]:
    rows, total = await crud_supplier.list_suppliers(db, page=page, size=size, keyword=keyword)
    items = [
        SupplierListItem(
            **SupplierOut.model_validate(supplier).model_dump(),
            order_count=count,
            total_amount=money(amount),
            last_order_at=last_at,
        )
        for supplier, count, amount, last_at in rows
    ]
    return Page[SupplierListItem](items=items, total=total, page=page, size=size, pages=calc_pages(total, size))


async def list_options(db: AsyncSession) -> list[SupplierOptionOut]:
    return [SupplierOptionOut.model_validate(s) for s in await crud_supplier.options(db)]


async def create_supplier(db: AsyncSession, payload: SupplierCreate) -> SupplierOut:
    supplier = await crud_supplier.create_supplier(db, payload.model_dump())
    await db.commit()
    await db.refresh(supplier)
    return _out(supplier)


async def update_supplier(db: AsyncSession, supplier_id: int, payload: SupplierUpdate) -> SupplierOut:
    supplier = await crud_supplier.get_by_id(db, supplier_id)
    if supplier is None:
        raise AppError("SUPPLIER_NOT_FOUND", "供应商不存在", 404)
    await crud_supplier.update_supplier(db, supplier, payload.model_dump(exclude_unset=True))
    await db.commit()
    await db.refresh(supplier)
    return _out(supplier)
