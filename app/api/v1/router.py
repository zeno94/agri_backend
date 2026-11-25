"""v1 路由聚合。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import (
    audit,
    auth,
    customers,
    dashboard,
    inventory,
    modules,
    parts,
    purchases,
    sales,
    suppliers,
    users,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(audit.router)
api_router.include_router(parts.router)
api_router.include_router(customers.router)
api_router.include_router(suppliers.router)
api_router.include_router(purchases.router)
api_router.include_router(sales.router)
api_router.include_router(dashboard.router)
api_router.include_router(inventory.router)
api_router.include_router(users.router)
api_router.include_router(modules.router)

__all__ = ["api_router"]
