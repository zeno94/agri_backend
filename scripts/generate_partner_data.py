"""一次性重造供应商/客户并重挂历史订单。

只修改：
- suppliers / customers 主数据；
- sale_orders.customer_id / purchase_orders.supplier_id；
- audit_logs 中销售/采购详情里的客户/供应商 ID 与名称。

订单号、金额、时间、库存流水一律不动。
"""

from __future__ import annotations

import asyncio
import json
import random
import re
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import delete, select, text

from app.db.session import SessionLocal, dispose_engine
from app.models.customer import Customer, CustomerFollowup
from app.models.part import Part
from app.models.purchase import PurchaseItem, PurchaseOrder
from app.models.sale import SaleItem, SaleOrder
from app.models.supplier import Supplier

RNG = random.Random(20261124)

SURNAMES = list(
    "王李张刘陈杨赵黄周孙马朱高郭何胡吴徐宋郑谢韩唐冯于董萧程曹袁邓许傅沈曾彭吕苏卢蒋蔡贾丁魏薛叶阎余潘杜戴夏钟汪田任姜范方石姚谭廖邹熊金陆郝孔白崔康毛邱秦江史顾侯邵孟龙万段雷钱汤尹黎易常武乔贺赖龚文"
)
MALE_GIVEN = re.findall(
    r".{2}",
    "建军建国建华国强国营国顺守业守田运来运粮德旺德顺金贵金坡保国保平广田广利丰年长海长顺玉堂玉良志强志刚永强永军红伟红建海军海涛春生春林明远明亮国亮振华振国新社新军新民建力建新清合清泉留柱扎根长柱二军三军",
)
FEMALE_GIVEN = re.findall(r".{2}", "玉兰秀英桂兰凤英秀兰桂英海燕春梅丽娟小红秀珍玉珍爱莲雪梅")
CUSTOMER_TYPES = ["种粮户", "农机手", "种粮大户", "经济作物", "蔬菜大棚", "其他"]

TYPE_PREFS = {
    "农机手": {"传动带", "刀片/农机具", "机油/润滑", "轴承", "制动/传动"},
    "种粮大户": {"滤清器", "机油/润滑", "轴承", "整机", "发动机件"},
    "种粮户": {"滤清器", "机油/润滑", "传动带", "紧固件", "制动/传动"},
    "经济作物": {"水泵", "灌溉水带", "植保配件", "刀片/农机具"},
    "蔬菜大棚": {"水泵", "灌溉水带", "植保配件"},
    "其他": {"传动带", "紧固件", "机油/润滑", "轴承"},
}

LOCAL_REGIONS = [
    (
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
        300,
    ),
    (
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
        110,
    ),
    ("五里河镇", ["五里河村", "刘庄村", "马庄村", "王庄村", "赵寨村", "岗刘村", "张阁村"], 100),
    (
        "裴村店乡",
        [
            "刘庄村",
            "王庄村",
            "李楼村",
            "裴村店村",
            "郭楼村",
            "朱楼村",
            "张唐村",
            "孟楼村",
            "史洼村",
            "祁楼村",
            "刘堂村",
            "回河村",
        ],
        90,
    ),
    ("金城街道", ["王庄村", "杨庄村", "陈庄村", "李楼村", "赵庄村", "刘庄村"], 100),
]

OTHER_REGIONS = [
    ("宗店乡", ["宗店村", "孙庄村", "刘寨村", "张庄村", "王楼村"], 30),
    ("高阳镇", ["高阳村", "马寨村", "王桥村", "张庄村", "陈庄村"], 25),
    ("苏木乡", ["苏木村", "周庄村", "刘庄村", "李庄村", "王庄村"], 20),
    ("板木乡", ["板木村", "张庄村", "刘庄村", "王庄村", "陈庄村"], 20),
    ("湖岗乡", ["湖岗村", "李庄村", "王庄村", "张庄村", "刘庄村"], 20),
    ("官庄乡", ["官庄村", "王庄村", "李庄村", "张庄村"], 15),
    ("竹林乡", ["竹林村", "刘庄村", "王庄村", "陈庄村"], 15),
    ("沙沃乡", ["沙沃村", "张庄村", "李庄村", "王庄村"], 15),
    ("阳堌镇", ["阳堌村", "张庄村", "王庄村", "刘庄村"], 20),
    ("葛岗镇", ["葛岗村", "李庄村", "王庄村", "张庄村"], 20),
]

NEIGHBOR_REGIONS = [
    ("通许县玉皇庙镇", ["吴楼村", "王庄村", "张庄村", "李庄村"], 30),
    ("尉氏县蔡庄镇", ["蔡庄村", "刘庄村", "王庄村", "李庄村"], 20),
    ("兰考县堌阳镇", ["堌阳村", "张庄村", "王庄村", "刘庄村"], 18),
    ("祥符区陈留镇", ["郭庄村", "王庄村", "李庄村", "张庄村"], 12),
    ("睢县蓼堤镇", ["蓼堤村", "刘庄村", "王庄村"], 10),
    ("民权县人和镇", ["人和村", "张庄村", "王庄村"], 10),
]

SUPPLIERS = [
    ("杞县鑫源农机销售有限公司", "杞县县城建设路", "张经理", ["整机", "农机具"], 1, "月结"),
    ("杞县丰农农机配件有限公司", "杞县县城北环路", "李经理", ["传动带", "轴承", "紧固件"], 1, "现结"),
    ("杞县中原农机配件销售中心", "杞县县城人民路", "王经理", ["滤清器", "机油/润滑"], 1, "现结"),
    ("杞县惠农水泵销售中心", "杞县县城南关", "刘经理", ["水泵", "灌溉水带"], 1, "现结"),
    ("杞县恒达农机配件有限公司", "杞县县城产业集聚区", "陈经理", ["传动带", "制动/传动"], 1, "月结"),
    ("杞县金田农机配件有限公司", "杞县县城西环路", "杨经理", ["刀片/农机具", "植保配件"], 1, "月结"),
    ("杞县兴农液压件销售中心", "杞县县城东关", "赵经理", ["液压件", "发动机件"], 1, "现结"),
    ("杞县诚信电器配件有限公司", "杞县县城建设路南段", "孙经理", ["电器/灯具", "紧固件"], 1, "现结"),
    ("开封市铭远农机配件有限公司", "开封市禹王台区农机大市场", "马经理", ["综合配件", "发动机件"], 2, "月结"),
    ("开封市豫东农业机械有限公司", "开封市南郊农机市场", "朱经理", ["整机", "刀片/农机具"], 2, "月结"),
    ("开封市沃野商贸有限公司", "开封市禹王台区物流园", "高经理", ["机油/润滑", "滤清器"], 2, "月结"),
    ("开封市中原轮胎销售有限公司", "开封市禹王台区农机大市场", "郭经理", ["轮胎", "制动/传动"], 2, "现结"),
    ("开封市福田农机配件有限公司", "开封市祥符区黄龙园区", "何经理", ["发动机件", "液压件"], 2, "月结"),
    ("开封市农友农机销售中心", "开封市禹王台区南郊", "胡经理", ["水泵", "灌溉水带"], 2, "现结"),
    ("开封市华盛农机配件有限公司", "开封市鼓楼区南苑", "吴经理", ["轴承", "传动带"], 2, "月结"),
    ("通许县农丰农机销售有限公司", "通许县城南环路", "徐经理", ["水泵", "灌溉水带"], 1, "现结"),
    ("通许县豫东农机配件有限公司", "通许县城北关", "宋经理", ["轴承", "传动带"], 1, "月结"),
    ("通许县宏达农机配件销售中心", "通许县城西关", "郑经理", ["滤清器", "机油/润滑"], 1, "现结"),
    ("尉氏县富田农机配件有限公司", "尉氏县城人民路", "谢经理", ["发动机件", "液压件"], 2, "月结"),
    ("尉氏县顺发农机销售有限公司", "尉氏县城北环路", "韩经理", ["整机", "刀片/农机具"], 2, "月结"),
    ("兰考县东方农机销售有限公司", "兰考县城建设路", "唐经理", ["轮胎", "制动/传动"], 2, "月结"),
    ("兰考县金土地农机配件有限公司", "兰考县城南关", "冯经理", ["植保配件", "水泵"], 2, "现结"),
    ("睢县豫东农机配件有限公司", "睢县县城中央大街", "于经理", ["电器/灯具", "紧固件"], 2, "月结"),
]


def _region_pool(regions: list[tuple], count: int) -> list[tuple[str, str, str]]:
    pool: list[tuple[str, str, str]] = []
    for town, villages, amount in regions:
        for index in range(amount):
            village = villages[index % len(villages)]
            label = (
                f"{town}{village}"
                if town.startswith(("通许", "尉氏", "兰考", "祥符", "睢县", "民权"))
                else f"{town}{village}"
            )
            pool.append((town, village, label))
        count -= amount
    if count != 0:
        raise ValueError(f"区域配额不匹配，剩余 {count}")
    RNG.shuffle(pool)
    return pool


def _phone(index: int) -> str:
    return f"1990378{1000 + index:04d}"


def _build_customers() -> list[dict]:
    region_pool = (
        _region_pool(LOCAL_REGIONS, 700) + _region_pool(OTHER_REGIONS, 200) + _region_pool(NEIGHBOR_REGIONS, 100)
    )

    tiers: list[str] = []
    for tier, amount in (("core", 150), ("regular", 350), ("occasional", 500)):
        tiers.extend([tier] * amount)

    type_quotas = {
        "core": ["农机手"] * 60 + ["种粮大户"] * 50 + ["经济作物"] * 40,
        "regular": ["种粮户"] * 120 + ["农机手"] * 80 + ["经济作物"] * 80 + ["蔬菜大棚"] * 70,
        "occasional": ["种粮户"] * 250 + ["经济作物"] * 100 + ["蔬菜大棚"] * 80 + ["其他"] * 70,
    }
    for values in type_quotas.values():
        RNG.shuffle(values)

    counts: dict[str, list[int]] = {
        "core": [27] * 69 + [26] * 81,
        "regular": [11] * 28 + [10] * 322,
        "occasional": [1] * 200 + [4] * 223 + [3] * 77,
    }
    for values in counts.values():
        RNG.shuffle(values)

    records = []
    tier_indices = {"core": [], "regular": [], "occasional": []}
    type_offsets = {"core": 0, "regular": 0, "occasional": 0}
    for index in range(1000):
        tier = tiers[index]
        type_values = type_quotas[tier]
        customer_type = type_values[type_offsets[tier]]
        type_offsets[tier] += 1
        count_index = len(tier_indices[tier])
        records.append(
            {
                "id": 1001 + index,
                "tier": tier,
                "order_count": counts[tier][count_index],
                "customer_type": customer_type,
            }
        )
        tier_indices[tier].append(index)

    # 分层客户中抽取 60 个只留姓+称谓、40 个完全未知。
    name_kind = ["full"] * 1000
    regular_idx = [i for i, r in enumerate(records) if r["tier"] == "regular"]
    occasional_idx = [i for i, r in enumerate(records) if r["tier"] == "occasional"]
    for i in RNG.sample(regular_idx, 20):
        name_kind[i] = "partial"
    for i in RNG.sample(occasional_idx, 40):
        name_kind[i] = "partial"
    for i in RNG.sample([i for i in occasional_idx if name_kind[i] == "full"], 40):
        name_kind[i] = "unknown"

    used_names: set[str] = set()
    used_phones: set[str] = set()
    customers: list[dict] = []
    crops_by_type = {
        "种粮户": ["小麦", "玉米"],
        "种粮大户": ["小麦", "玉米"],
        "农机手": ["小麦", "玉米"],
        "经济作物": ["大蒜", "花生"],
        "蔬菜大棚": ["蔬菜"],
        "其他": [],
    }
    acreage_by_tier = {
        "core": (30, 180),
        "regular": (10, 80),
        "occasional": (3, 25),
    }

    for index, record in enumerate(records):
        town, village, label = region_pool[index]
        kind = name_kind[index]
        surname = RNG.choice(SURNAMES)
        if kind == "unknown":
            display = f"未知（{label}）"
            phone = None if index % 2 == 0 else _phone(index)
        elif kind == "partial":
            title = "先生" if RNG.random() < 0.62 else "女士"
            display = f"{surname}{title}（{label}）"
            phone = _phone(index)
        else:
            female = RNG.random() < 0.18
            given = RNG.choice(FEMALE_GIVEN if female else MALE_GIVEN)
            display = f"{surname}{given}（{label}）"
            # 同名同村时换一个名字，保证完整姓名可区分。
            attempts = 0
            while display in used_names and attempts < 30:
                given = RNG.choice(FEMALE_GIVEN if female else MALE_GIVEN)
                display = f"{surname}{given}（{label}）"
                attempts += 1
            phone = _phone(index)

        used_names.add(display)
        if phone and phone in used_phones:
            raise RuntimeError(f"手机号重复：{phone}")
        if phone:
            used_phones.add(phone)

        low, high = acreage_by_tier[record["tier"]]
        acreage = None if kind == "unknown" and RNG.random() < 0.3 else Decimal(str(RNG.randint(low, high)))
        tags = []
        if record["tier"] == "core":
            tags.append("核心客户")
        elif record["tier"] == "regular":
            tags.append("常客")
        else:
            tags.append("散客")
        if record["customer_type"] != "其他":
            tags.append(record["customer_type"])
        if RNG.random() < 0.35:
            tags.append("可送货")
        if RNG.random() < 0.18:
            tags.append("价格敏感")
        if kind != "full":
            tags.append("未留全名")

        next_follow_up = None
        if record["tier"] in {"core", "regular"}:
            next_follow_up = (datetime.now(UTC).replace(tzinfo=None) + timedelta(days=RNG.randint(1, 30))).replace(
                hour=RNG.randint(8, 18), minute=RNG.choice([0, 15, 30, 45]), second=0, microsecond=0
            )

        customers.append(
            {
                "id": record["id"],
                "name": display,
                "phone": phone,
                "town": town,
                "village": village,
                "customer_type": record["customer_type"],
                "acreage": acreage,
                "main_crops": crops_by_type[record["customer_type"]],
                "tags": tags,
                "note": None,
                "next_follow_up_at": next_follow_up,
                "is_active": True,
                "created_at": datetime(2021, 6, 1) + timedelta(days=index % 300),
                "updated_at": datetime(2021, 6, 1) + timedelta(days=index % 300),
                "tier": record["tier"],
                "order_count": record["order_count"],
                "name_kind": kind,
            }
        )

    return customers


def _build_suppliers() -> list[dict]:
    records = []
    for index, (name, address, contact, categories, delivery, terms) in enumerate(SUPPLIERS):
        records.append(
            {
                "id": 101 + index,
                "name": name,
                "phone": f"199037801{index + 1:02d}",
                "address": address,
                "contact_person": contact,
                "main_categories": categories,
                "delivery_days": delivery,
                "payment_terms": terms,
                "note": None,
                "is_active": True,
                "created_at": datetime(2021, 6, 1) + timedelta(days=index),
                "updated_at": datetime(2021, 6, 1) + timedelta(days=index),
            }
        )
    return records


def _weighted_choice(candidates, weights):
    total = sum(weights)
    if total <= 0:
        return RNG.choice(candidates)
    point = RNG.random() * total
    for item, weight in zip(candidates, weights, strict=True):
        point -= weight
        if point <= 0:
            return item
    return candidates[-1]


async def main() -> None:
    customers_data = _build_customers()
    suppliers_data = _build_suppliers()

    async with SessionLocal() as db:
        existing = await db.scalar(select(Customer.id).where(Customer.id >= 1001).limit(1))
        if existing is not None:
            raise SystemExit("检测到新客户数据已存在；本脚本为一次性生成，请先恢复备份。")

        for item in suppliers_data:
            db.add(Supplier(**{k: v for k, v in item.items()}))
        for item in customers_data:
            payload = {k: v for k, v in item.items() if k not in {"tier", "order_count", "name_kind"}}
            db.add(Customer(**payload))
        await db.flush()

        # 供应商按品类配额分配采购单：前 9 家 9 单，其余 8 单，合计 193。
        purchase_orders = list((await db.scalars(select(PurchaseOrder))).all())
        purchase_categories = defaultdict(set)
        purchase_rows = (
            await db.execute(select(PurchaseItem.order_id, Part.category).join(Part, Part.id == PurchaseItem.part_id))
        ).all()
        for order_id, category in purchase_rows:
            purchase_categories[order_id].add(category or "未分类")
        supplier_quota = {s["id"]: 9 if i < 9 else 8 for i, s in enumerate(suppliers_data)}
        supplier_by_id = {s["id"]: s for s in suppliers_data}
        purchase_orders.sort(key=lambda order: (len(purchase_categories[order.id]), -float(order.total_amount)))
        for order in purchase_orders:
            candidates = [sid for sid, remaining in supplier_quota.items() if remaining > 0]
            weights = [
                1 + 8 * len(purchase_categories[order.id] & set(supplier_by_id[sid]["main_categories"]))
                for sid in candidates
            ]
            chosen = _weighted_choice(candidates, weights)
            supplier_quota[chosen] -= 1
            order.supplier_id = chosen
        if any(supplier_quota.values()):
            raise RuntimeError(f"采购单分配未清空：{supplier_quota}")

        # 客户按层级/品类偏好分配销售单；每户配额在 _build_customers 中已经固定。
        sale_orders = list((await db.scalars(select(SaleOrder))).all())
        sale_categories = defaultdict(set)
        sale_rows = (
            await db.execute(select(SaleItem.order_id, Part.category).join(Part, Part.id == SaleItem.part_id))
        ).all()
        for order_id, category in sale_rows:
            sale_categories[order_id].add(category or "未分类")

        remaining = {c["id"]: c["order_count"] for c in customers_data}
        customer_by_id = {c["id"]: c for c in customers_data}
        sale_orders.sort(key=lambda order: -float(order.total_amount))
        for order in sale_orders:
            candidates = [cid for cid, count in remaining.items() if count > 0]
            weights = []
            for cid in candidates:
                customer = customer_by_id[cid]
                tier_weight = {"core": 3.0, "regular": 1.8, "occasional": 1.0}[customer["tier"]]
                overlap = len(sale_categories[order.id] & TYPE_PREFS[customer["customer_type"]])
                weight = tier_weight * (1 + 6 * overlap)
                if customer["tier"] == "core" and float(order.total_amount) >= 300:
                    weight *= 2
                if customer["tier"] == "occasional" and float(order.total_amount) < 100:
                    weight *= 2
                weights.append(weight)
            chosen = _weighted_choice(candidates, weights)
            remaining[chosen] -= 1
            order.customer_id = chosen
        if any(remaining.values()):
            raise RuntimeError(f"销售单分配未清空：{sum(remaining.values())}")

        await db.commit()

        # 删除迁移前遗留的旧主数据；订单已经全部指向新 ID。
        await db.execute(delete(CustomerFollowup).where(CustomerFollowup.customer_id < 1000))
        await db.execute(delete(Customer).where(Customer.id < 1000))
        await db.execute(delete(Supplier).where(Supplier.id < 100))
        await db.execute(
            text(
                "DELETE FROM audit_logs WHERE action IN ('customer.create','supplier.create') " "AND resource_id < 1000"
            )
        )
        await db.execute(
            text(
                """
                UPDATE audit_logs a
                JOIN sale_orders o
                  ON a.action = 'sale.outbound'
                 AND JSON_UNQUOTE(JSON_EXTRACT(a.detail, '$.order_no')) = o.order_no
                JOIN customers c ON c.id = o.customer_id
                SET a.detail = JSON_SET(
                    a.detail,
                    '$.customer_id', o.customer_id,
                    '$.customer_name', c.name
                )
                WHERE a.action = 'sale.outbound' AND a.detail IS NOT NULL
                """
            )
        )
        await db.execute(
            text(
                """
                UPDATE audit_logs a
                JOIN purchase_orders o
                  ON a.action = 'purchase.inbound'
                 AND JSON_UNQUOTE(JSON_EXTRACT(a.detail, '$.order_no')) = o.order_no
                JOIN suppliers s ON s.id = o.supplier_id
                SET a.detail = JSON_SET(
                    a.detail,
                    '$.supplier_id', o.supplier_id,
                    '$.supplier_name', s.name
                )
                WHERE a.action = 'purchase.inbound' AND a.detail IS NOT NULL
                """
            )
        )
        await db.commit()

    stats = {
        "customers": len(customers_data),
        "suppliers": len(suppliers_data),
        "sales": sum(c["order_count"] for c in customers_data),
        "purchases": 193,
        "full_names": sum(c["name_kind"] == "full" for c in customers_data),
        "partial_names": sum(c["name_kind"] == "partial" for c in customers_data),
        "unknown_names": sum(c["name_kind"] == "unknown" for c in customers_data),
        "core": sum(c["tier"] == "core" for c in customers_data),
        "regular": sum(c["tier"] == "regular" for c in customers_data),
        "occasional": sum(c["tier"] == "occasional" for c in customers_data),
    }
    Path("/tmp/partner_data_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2))
    print(json.dumps(stats, ensure_ascii=False, indent=2))


async def _run() -> None:
    try:
        await main()
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(_run())
