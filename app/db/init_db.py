"""初始化基础数据（幂等，可重复执行）。

用法：
    python -m app.db.init_db

创建：老板账号、员工账号、示例往来单位、示例配件（含期初库存流水）。
不会创建示例订单，订单请通过接口产生，以保证库存与流水始终一致。
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, dispose_engine, engine
from app.models.enums import ChangeType, PartnerType, UserRole
from app.models.inventory_log import InventoryLog
from app.models.part import Part
from app.models.partner import Partner
from app.models.user import User

logger = get_logger(__name__)

SAMPLE_PARTNERS: list[dict[str, Any]] = [
    {"name": "山东潍坊农机配件有限公司", "type": PartnerType.SUPPLIER.value, "phone": "0536-8888666"},
    {"name": "江苏常州发动机配件厂", "type": PartnerType.SUPPLIER.value, "phone": "0519-6666888"},
    {"name": "绿野农机专业合作社", "type": PartnerType.CUSTOMER.value, "phone": "13800001111"},
    {"name": "丰收家庭农场", "type": PartnerType.CUSTOMER.value, "phone": "13900002222"},
]

SAMPLE_PARTS: list[dict[str, Any]] = [
    {
        "name": "柴油滤清器",
        "model": "4L88",
        "category": "滤清器",
        "brand": "潍柴",
        "stock": 50,
        "safe_stock": 20,
        "purchase_price": Decimal("12.50"),
        "sale_price": Decimal("25.00"),
    },
    {
        "name": "机油滤清器",
        "model": "JX0810",
        "category": "滤清器",
        "brand": "一拖",
        "stock": 8,
        "safe_stock": 15,
        "purchase_price": Decimal("8.00"),
        "sale_price": Decimal("16.00"),
    },
    {
        "name": "拖拉机前照灯",
        "model": "FT-12V",
        "category": "灯具",
        "brand": "福田",
        "stock": 30,
        "safe_stock": 10,
        "purchase_price": Decimal("45.00"),
        "sale_price": Decimal("88.00"),
    },
    {
        "name": "液压油缸",
        "model": "3200",
        "category": "液压件",
        "brand": "约翰迪尔",
        "stock": 3,
        "safe_stock": 5,
        "purchase_price": Decimal("680.00"),
        "sale_price": Decimal("1280.00"),
    },
    {
        "name": "三轮车刹车片",
        "model": "SF-200",
        "category": "制动系统",
        "brand": "时风",
        "stock": 100,
        "safe_stock": 30,
        "purchase_price": Decimal("6.50"),
        "sale_price": Decimal("15.00"),
    },
    {
        "name": "收割机皮带",
        "model": "B-1800",
        "category": "传动件",
        "brand": "久保田",
        "stock": 12,
        "safe_stock": 12,
        "purchase_price": Decimal("28.00"),
        "sale_price": Decimal("55.00"),
    },
    {
        "name": "植保机喷头",
        "model": "AG-01",
        "category": "植保配件",
        "brand": "大疆",
        "stock": 0,
        "safe_stock": 10,
        "purchase_price": Decimal("35.00"),
        "sale_price": Decimal("68.00"),
    },
    {
        "name": "柴油机缸套",
        "model": "CC-195",
        "category": "发动机件",
        "brand": "常柴",
        "stock": 25,
        "safe_stock": 8,
        "purchase_price": Decimal("55.00"),
        "sale_price": Decimal("110.00"),
    },
]


async def _ensure_user(db: AsyncSession, username: str, password: str, role: UserRole) -> User:
    user = await db.scalar(select(User).where(User.username == username))
    if user is not None:
        return user
    user = User(username=username, password_hash=hash_password(password), role=role.value)
    db.add(user)
    await db.flush()
    logger.info("创建用户：%s（%s）", username, role.value)
    return user


async def _ensure_partner(db: AsyncSession, data: dict[str, Any]) -> None:
    exists = await db.scalar(
        select(Partner.id).where(Partner.name == data["name"], Partner.type == data["type"])
    )
    if exists is None:
        db.add(Partner(**data))
        logger.info("创建往来单位：%s", data["name"])


async def _ensure_part(db: AsyncSession, data: dict[str, Any], operator: User) -> None:
    exists = await db.scalar(
        select(Part.id).where(
            Part.name == data["name"],
            Part.model == data["model"],
            Part.brand == data["brand"],
        )
    )
    if exists is not None:
        return

    part = Part(**data)
    db.add(part)
    await db.flush()
    if part.stock > 0:
        db.add(
            InventoryLog(
                part_id=part.id,
                change_type=ChangeType.CHECK.value,
                change_qty=part.stock,
                before_stock=0,
                after_stock=part.stock,
                operator_id=operator.id,
                remark="初始化示例数据-期初库存",
            )
        )
    logger.info("创建配件：%s（%s）库存 %s", part.name, part.model, part.stock)


async def seed() -> None:
    if settings.AUTO_CREATE_TABLES:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as db:
        boss = await _ensure_user(db, settings.SEED_BOSS_USERNAME, settings.SEED_BOSS_PASSWORD, UserRole.BOSS)
        await _ensure_user(db, settings.SEED_EMPLOYEE_USERNAME, settings.SEED_EMPLOYEE_PASSWORD, UserRole.EMPLOYEE)

        for partner_data in SAMPLE_PARTNERS:
            await _ensure_partner(db, partner_data)

        for part_data in SAMPLE_PARTS:
            await _ensure_part(db, dict(part_data), boss)

        await db.commit()

    logger.info("基础数据初始化完成")


async def main() -> None:
    setup_logging()
    try:
        await seed()
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
