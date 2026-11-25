"""客户类型/作物/面积/下次跟进 + 供应商电话刷新。"""

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.db.session import SessionLocal, dispose_engine
from app.models.customer import Customer
from app.models.supplier import Supplier

RNG = random.Random(20261124)

MOBILE_PREFIXES = [
    "1380378",
    "1390378",
    "1370378",
    "1360378",
    "1350378",
    "1500378",
    "1510378",
    "1520378",
    "1570378",
    "1580378",
    "1590378",
    "1820378",
    "1830378",
    "1870378",
    "1880378",
    "1300378",
    "1310378",
    "1320378",
    "1550378",
    "1560378",
    "1850378",
    "1860378",
    "1330378",
    "1530378",
    "1730378",
    "1770378",
    "1800378",
    "1810378",
    "1890378",
    "1990378",
]


def _mobile() -> str:
    return RNG.choice(MOBILE_PREFIXES) + f"{RNG.randint(0, 9999):04d}"


def _landline(address: str) -> str:
    area = "0370" if "睢县" in address else "0371"
    return f"{area}-{RNG.randint(20_000_000, 29_999_999)}"


async def main() -> None:
    async with SessionLocal() as db:
        customers = list((await db.scalars(select(Customer).order_by(Customer.id))).all())
        for customer in customers:
            customer.customer_type = "其他"
            customer.main_crops = ["其他"]
            customer.acreage = Decimal("0.0")
            if "核心客户" in (customer.tags or []):
                now = datetime(2026, 11, 24, 9, 0, 0)
                customer.next_follow_up_at = now + timedelta(
                    days=RNG.randint(1, 30),
                    hours=RNG.randint(8, 18),
                    minutes=RNG.choice([0, 15, 30, 45]),
                )

        suppliers = list((await db.scalars(select(Supplier).order_by(Supplier.id))).all())
        used: set[str] = set()
        for index, supplier in enumerate(suppliers):
            # 本地公司一半用固定电话，一半用开封 0378 手机号，避免全是一串连号。
            use_landline = index % 2 == 0
            while True:
                phone = _landline(supplier.address or "") if use_landline else _mobile()
                if phone not in used:
                    used.add(phone)
                    supplier.phone = phone
                    break
        await db.commit()

    print(f"customers={len(customers)}, suppliers={len(suppliers)}")


async def _run() -> None:
    try:
        await main()
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(_run())
