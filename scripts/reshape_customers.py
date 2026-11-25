"""按业务口径重塑客户：地址字段、手机号、标签、作物与新增 76 户。

一次性脚本，执行前请备份数据库。
"""

from __future__ import annotations

import asyncio
import json
import random
import re
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select, text

from app.db.session import SessionLocal, dispose_engine
from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.sale import SaleOrder

RNG = random.Random(20261124)

PHONE_PREFIXES = [
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

SURNAMES = list(
    "王李张刘陈杨赵黄周孙马朱高郭何胡吴徐宋郑谢韩唐冯于董萧程曹袁邓许傅沈曾彭吕苏卢蒋蔡贾丁魏薛叶阎余潘杜戴夏钟汪田任姜范方石姚谭廖邹熊金陆郝孔白崔康毛邱秦江史顾侯邵孟龙万段雷钱汤尹黎易常武乔贺赖龚文"
)
MALE_GIVEN = re.findall(
    r".{2}",
    "建军建国建华国强国营国顺守业守田运来运粮德旺德顺金贵金坡保国保平广田广利丰年长海长顺玉堂玉良志强志刚永强永军红伟红建海军海涛春生春林明远明亮国亮振华振国新社新军新民建力建新清合清泉留柱扎根长柱二军三军",
)
FEMALE_GIVEN = re.findall(r".{2}", "玉兰秀英桂兰凤英秀兰桂英海燕春梅丽娟小红秀珍玉珍爱莲雪梅")

LOCAL_POOL = [
    (
        "杞县",
        "邢口镇",
        [
            "冷屯村",
            "杨屯村",
            "袁寨村",
            "王寺寨村",
            "孙洼村",
            "邢北村",
            "邢南村",
            "谢寨村",
            "夏寨村",
            "黄寨村",
            "魏寨村",
            "何寨村",
            "潘屯村",
            "肖胡同村",
            "卢楼村",
            "草寺村",
            "姜楼村",
            "马庙村",
            "田寨村",
            "薛楼村",
            "岳楼村",
            "梅湾村",
            "小河寨村",
            "河沿村",
        ],
        20,
    ),
    (
        "杞县",
        "傅集镇",
        [
            "周庄村",
            "杨庄村",
            "宋庄村",
            "五里井村",
            "军张村",
            "纸房村",
            "庞屯村",
            "谢洼村",
            "陆庄村",
            "曹胡同村",
            "老庄村",
            "傅集北村",
            "傅集南村",
        ],
        8,
    ),
    ("杞县", "五里河镇", ["五里河村", "刘庄村", "马庄村", "王庄村", "赵寨村", "岗刘村", "张阁村"], 7),
    (
        "杞县",
        "裴村店乡",
        [
            "刘庄村",
            "王庄村",
            "李楼村",
            "裴村店村",
            "郭楼村",
            "朱楼村",
            "张堂村",
            "孟楼村",
            "史洼村",
            "祁楼村",
            "刘堂村",
            "回河村",
        ],
        6,
    ),
    ("杞县", "金城街道", ["王庄村", "杨庄村", "陈庄村", "李楼村", "赵庄村", "刘庄村"], 9),
    ("杞县", "宗店乡", ["宗店村", "孙庄村", "刘寨村", "张庄村", "王楼村"], 4),
    ("杞县", "高阳镇", ["高阳村", "马寨村", "王桥村", "张庄村", "陈庄村"], 4),
    ("杞县", "苏木乡", ["苏木村", "周庄村", "刘庄村", "李庄村", "王庄村"], 3),
    ("杞县", "板木乡", ["板木村", "张庄村", "刘庄村", "王庄村", "陈庄村"], 3),
    ("杞县", "湖岗乡", ["湖岗村", "李庄村", "王庄村", "张庄村"], 3),
    ("杞县", "阳堌镇", ["阳堌村", "张庄村", "王庄村", "刘庄村"], 3),
    ("通许县", "玉皇庙镇", ["吴楼村", "王庄村", "张庄村", "李庄村"], 2),
    ("尉氏县", "蔡庄镇", ["蔡庄村", "刘庄村", "王庄村", "李庄村"], 1),
    ("兰考县", "堌阳镇", ["堌阳村", "张庄村", "王庄村", "刘庄村"], 1),
    ("祥符区", "陈留镇", ["郭庄村", "王庄村", "李庄村", "张庄村"], 1),
    ("睢县", "蓼堤镇", ["蓼堤村", "刘庄村", "王庄村"], 1),
]


def _region_rows() -> list[tuple[str, str, str, str]]:
    rows = []
    for county, town, villages, count in LOCAL_POOL:
        city = "商丘市" if county in {"睢县", "民权县"} else "开封市"
        for index in range(count):
            rows.append((city, county, town, villages[index % len(villages)]))
    if len(rows) != 76:
        raise RuntimeError(f"新增客户区域配额不是 76：{len(rows)}")
    RNG.shuffle(rows)
    return rows


def _split_town(city: str, county: str, town: str | None) -> tuple[str, str, str | None]:
    if not town:
        return city, county, town
    for prefix, city_name, county_name in (
        ("通许县", "开封市", "通许县"),
        ("尉氏县", "开封市", "尉氏县"),
        ("兰考县", "开封市", "兰考县"),
        ("祥符区", "开封市", "祥符区"),
        ("睢县", "商丘市", "睢县"),
        ("民权县", "商丘市", "民权县"),
    ):
        if town.startswith(prefix):
            return city_name, county_name, town[len(prefix) :]
    return city, county, town


def _new_phone(prefix: str) -> str:
    return prefix + f"{RNG.randint(0, 9999):04d}"


def _display_name(name: str) -> str:
    return re.sub(r"（.*）$", "", name).strip()


def _audit_detail(customer: Customer) -> dict:
    address = "".join(filter(None, [customer.city, customer.county, customer.town, customer.village]))
    return {
        "name": customer.name,
        "phone": customer.phone,
        "city": customer.city,
        "county": customer.county,
        "town": customer.town,
        "village": customer.village,
        "address": address,
    }


async def main() -> None:
    async with SessionLocal() as db:
        customers = list((await db.scalars(select(Customer).order_by(Customer.id))).all())
        if len(customers) != 1000:
            raise SystemExit(f"预期 1000 个客户，实际 {len(customers)}；请先确认数据状态")

        for customer in customers:
            customer.name = _display_name(customer.name)
            city, county, town = _split_town(customer.city, customer.county, customer.town)
            customer.city = city
            customer.county = county
            customer.town = town
            customer.customer_type = "其他"
            customer.main_crops = ["其他"]

        # 追加 76 户，ID 从 2001 开始；不新增销售单。
        used_phones = {c.phone for c in customers if c.phone}
        used_names: set[tuple[str, str, str, str, str]] = set()
        new_customers: list[Customer] = []
        for index, (city, county, town, village) in enumerate(_region_rows(), start=1):
            while True:
                surname = RNG.choice(SURNAMES)
                if index <= 5:
                    display = f"{surname}{'先生' if RNG.random() < 0.6 else '女士'}"
                elif index <= 8:
                    display = "未知"
                else:
                    display = surname + RNG.choice(MALE_GIVEN if RNG.random() < 0.8 else FEMALE_GIVEN)
                key = (display, city, county, town, village)
                if key not in used_names:
                    used_names.add(key)
                    break
            while True:
                phone = _new_phone(RNG.choice(PHONE_PREFIXES))
                if phone not in used_phones:
                    used_phones.add(phone)
                    break
            is_relative = index <= 6
            customer = Customer(
                id=2000 + index,
                name=display,
                phone=phone,
                city=city,
                county=county,
                town=town,
                village=village,
                customer_type="其他",
                acreage=Decimal("0.0"),
                main_crops=["其他"],
                tags=["核心客户"] if is_relative else ["其他"],
                note="亲戚" if is_relative else None,
                is_active=True,
                created_at=datetime(2026, 11, 24, 8, 0, 0) + timedelta(minutes=index),
                updated_at=datetime(2026, 11, 24, 8, 0, 0) + timedelta(minutes=index),
            )
            db.add(customer)
            new_customers.append(customer)

        await db.flush()

        # 统一重发手机号：开封 0378 号段、随机尾号，不再使用 199 顺序号。
        all_customers = customers + new_customers
        used_phones = set()
        for customer in all_customers:
            while True:
                phone = _new_phone(RNG.choice(PHONE_PREFIXES))
                if phone not in used_phones:
                    used_phones.add(phone)
                    customer.phone = phone
                    break

        # 核心客户 = 购买次数 >= 15 或 金额 >= 5000；新客户里的 6 个亲戚保持核心。
        stats = (
            await db.execute(
                select(
                    SaleOrder.customer_id,
                    func.count(SaleOrder.id),
                    func.coalesce(func.sum(SaleOrder.total_amount), 0),
                ).group_by(SaleOrder.customer_id)
            )
        ).all()
        stat_map = {int(cid): (int(count), Decimal(str(amount or 0))) for cid, count, amount in stats}
        for customer in customers:
            count, amount = stat_map.get(customer.id, (0, Decimal("0")))
            customer.tags = ["核心客户"] if count >= 15 or amount >= 5000 else ["其他"]

        # 销售备注统一清空，默认为空。
        await db.execute(text("UPDATE sale_orders SET remark = NULL"))

        # 给新增 76 户补客户创建操作记录，方便审计里看到这批数据的来源。
        admin = await db.scalar(text("SELECT id FROM users WHERE username='admin' LIMIT 1"))
        for seq, customer in enumerate(new_customers, start=1):
            db.add(
                AuditLog(
                    user_id=int(admin) if admin is not None else None,
                    username="admin",
                    role="boss",
                    action="customer.create",
                    module="customers",
                    resource_type="customer",
                    resource_id=customer.id,
                    method="POST",
                    path="/api/v1/customers",
                    status_code=201,
                    success=True,
                    detail=_audit_detail(customer),
                    created_at=datetime(2026, 11, 24, 9, 0, 0) + timedelta(minutes=seq),
                )
            )

        await db.commit()

    summary = {
        "customers": len(customers) + len(new_customers),
        "new_customers": len(new_customers),
        "core": sum(1 for c in all_customers if "核心客户" in (c.tags or [])),
        "other": sum(1 for c in all_customers if "其他" in (c.tags or [])),
        "phones": len({c.phone for c in all_customers}),
        "cities": sorted({c.city for c in all_customers}),
    }
    Path("/tmp/reshape_customer_stats.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


async def _run() -> None:
    try:
        await main()
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(_run())
