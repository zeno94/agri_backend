"""v1 路由聚合。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import auth, dashboard, inventory, partners, parts, purchases, sales

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(parts.router)
api_router.include_router(partners.router)
api_router.include_router(purchases.router)
api_router.include_router(sales.router)
api_router.include_router(dashboard.router)
api_router.include_router(inventory.router)

__all__ = ["api_router"]
