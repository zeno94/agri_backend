"""【旧版，已停用】生成 2022-09-12 ~ 2026-10-01 的农机配件 ERP 历史演示数据。

当前数据库已拆分为 customers / suppliers，并加入 modules / user_modules；
本脚本仍写 partners + partner_id，运行会覆盖 sql/seed... 为不兼容的新 schema。
请使用 scripts/generate_partner_data.py 重造客户/供应商，完整快照见 sql/seed...。

产物：
- sql/seed_2022_09_12_2026_10_01.sql：DBeaver 可执行的重建业务数据脚本
- sql/seed_stats.json：数据规模、营收、毛利、日期范围等统计

设计：
- 保留 users 表；清空 parts/partners/orders/items/logs/audit_logs 后重新插入；
- 价格来自公开农机/电商价格区间（见 sql/DATA_SOURCES.md），按品牌/型号分档；
- 订单按淡旺季、工作日、春节等因素生成，库存逐笔仿真，保证任何时点不为负；
- 销售明细记录实际成交单价，订单记录实际总金额；
- 审计日志覆盖登录/失败登录/退出、采购、销售、看板、日志查看、配件改价等操作；
- 时间统一：本地 Asia/Shanghai 生成，写入 UTC（与应用存储一致）。

用法：
    .venv/bin/python scripts/generate_historical_sql.py
"""

from __future__ import annotations

import base64
import hashlib
import json
import random
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import bcrypt

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "sql"
SQL_PATH = SQL_DIR / "seed_2022_09_12_2026_10_01.sql"
STATS_PATH = SQL_DIR / "seed_stats.json"

TZ = ZoneInfo("Asia/Shanghai")
START_DAY = date(2022, 9, 12)
END_DAY = date(2026, 10, 1)
RNG = random.Random(20261118)
MONEY = Decimal("0.01")

USER_DEFS = {
    "admin": {"password": "Boss@123456", "role": "boss"},
    "staff": {"password": "Staff@123456", "role": "employee"},
    "staff01": {"password": "Staff01@123456", "role": "employee"},
}
USER_WEIGHTS = {"admin": 0.12, "staff": 0.58, "staff01": 0.30}

ROLE_LABELS = {"boss": "老板", "employee": "员工"}


def hash_password(password: str) -> str:
    prehash = base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())
    return bcrypt.hashpw(prehash, bcrypt.gensalt(rounds=12)).decode("utf-8")


def money(value: Decimal | str | int) -> Decimal:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def local_dt(day: date, hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute, second), tzinfo=TZ)


def utc_naive(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None)


def sql_dt(value: datetime) -> str:
    return "'" + utc_naive(value).strftime("%Y-%m-%d %H:%M:%S") + "'"


def sql_str(value: str | None) -> str:
    if value is None:
        return "NULL"
    escaped = str(value).replace("\\", "\\\\").replace("'", "''")
    return "'" + escaped + "'"


def sql_num(value: Decimal | int) -> str:
    return format(value, "f") if isinstance(value, Decimal) else str(value)


@dataclass(frozen=True)
class Product:
    id: int
    name: str
    model: str
    category: str
    brand: str
    cost: Decimal
    retail: Decimal
    kind: str
    weight: float
    initial_stock: int
    reorder: int
    replenish: int
    max_qty: int


@dataclass(frozen=True)
class Partner:
    id: int
    name: str
    type: str
    phone: str


def _profile(cost: Decimal, kind: str) -> tuple[int, int, int, int]:
    if kind == "machinery":
        return 4, 2, 3, 1
    if kind == "large":
        return 12, 4, 15, 2
    if kind == "medium":
        return 45, 15, 60, 3
    if cost < Decimal("20"):
        return 240, 85, 300, 10
    if cost < Decimal("80"):
        return 150, 50, 190, 8
    return 90, 30, 120, 5


RAW_PRODUCTS: list[tuple[str, str, str, str, str, str, str, float]] = [
    # 整机 / 脱粒机
    ("稻麦脱粒机 5TG-70", "5TG-70", "整机", "东川", "480", "680", "machinery", 0.05),
    ("玉米脱粒机 5TG-70", "5TG-70", "整机", "城北", "520", "750", "machinery", 0.05),
    ("玉米脱粒机 5TY-80", "5TY-80", "整机", "沃得", "1600", "2100", "machinery", 0.04),
    ("稻麦脱粒机 5TG-100", "5TG-100", "整机", "雷沃", "2800", "3600", "machinery", 0.03),
    ("稻麦脱粒机 5TG-125", "5TG-125", "整机", "久保田", "6800", "8500", "machinery", 0.015),
    ("玉米脱粒机 5TY-90", "5TY-90", "整机", "常发", "2300", "3000", "machinery", 0.035),
    # 水泵
    ("汽油水泵 2寸", "2寸汽油泵", "水泵", "大江", "480", "660", "large", 0.55),
    ("汽油水泵 3寸", "3寸汽油泵", "水泵", "大江", "780", "1050", "large", 0.3),
    ("柴油水泵 2寸", "2寸柴油泵", "水泵", "常柴", "900", "1200", "large", 0.28),
    ("柴油水泵 3寸", "3寸柴油泵", "水泵", "常柴", "1500", "1950", "large", 0.22),
    ("柴油水泵 4寸", "4寸柴油泵", "水泵", "隆鑫", "2700", "3400", "machinery", 0.08),
    ("汽油水泵 2寸", "2寸本田泵", "水泵", "本田", "1200", "1550", "large", 0.12),
    ("污水泵 2寸", "2寸污水泵", "水泵", "大江", "650", "880", "large", 0.2),
    ("柴油水泵 4寸", "4寸常柴泵", "水泵", "常柴", "2900", "3650", "machinery", 0.07),
    # 水带
    ("农用灌溉水带 1.5寸 30米", "1.5寸-30m", "灌溉水带", "奔新农", "65", "95", "small", 0.7),
    ("农用灌溉水带 2寸 30米", "2寸-30m", "灌溉水带", "奔新农", "105", "150", "small", 0.75),
    ("农用灌溉水带 3寸 30米", "3寸-30m", "灌溉水带", "奔新农", "170", "240", "medium", 0.4),
    ("农用灌溉水带 4寸 30米", "4寸-30m", "灌溉水带", "奔新农", "260", "360", "medium", 0.22),
    ("农用灌溉水带 2寸 20米", "2寸-20m", "灌溉水带", "OEMG", "75", "110", "small", 0.45),
    # 三角带 / 齿形带
    ("三角带 A900", "A900", "传动带", "三维", "3.5", "6", "small", 1.1),
    ("三角带 A1000", "A1000", "传动带", "三维", "4", "6.8", "small", 1.2),
    ("三角带 B1200", "B1200", "传动带", "三维", "6", "10", "small", 1.0),
    ("三角带 B1500", "B1500", "传动带", "三维", "7", "12", "small", 1.0),
    ("三角带 B1800", "B1800", "传动带", "三维", "8.5", "14", "small", 1.0),
    ("三角带 A1000", "A1000", "传动带", "三力士", "4.8", "8", "small", 0.9),
    ("三角带 B1800", "B1800", "传动带", "三力士", "9", "15", "small", 0.9),
    ("三角带 A1200", "A1200", "传动带", "盖茨", "12", "20", "small", 0.5),
    ("三角带 B2000", "B2000", "传动带", "盖茨", "20", "32", "small", 0.4),
    ("三角带 A900", "A900", "传动带", "久龙", "3.2", "5.5", "small", 0.8),
    ("三角带 B1500", "B1500", "传动带", "久龙", "6.5", "11", "small", 0.8),
    ("三角带 C2500", "C2500", "传动带", "三维", "18", "30", "small", 0.3),
    ("齿形带 8M-1200", "8M-1200", "传动带", "三维", "15", "26", "small", 0.35),
    ("齿形带 8M-1600", "8M-1600", "传动带", "盖茨", "20", "34", "small", 0.3),
    # 紧固件
    ("外六角螺栓 M8×30 8.8级 100只/盒", "M8×30", "紧固件", "晋亿", "16", "28", "small", 1.5),
    ("外六角螺栓 M10×40 8.8级 100只/盒", "M10×40", "紧固件", "晋亿", "24", "38", "small", 1.6),
    ("外六角螺栓 M12×50 8.8级 100只/盒", "M12×50", "紧固件", "晋亿", "36", "55", "small", 1.3),
    ("外六角螺栓 M16×60 8.8级 100只/盒", "M16×60", "紧固件", "晋亿", "70", "105", "small", 0.7),
    ("内六角螺栓 M8×30 100只/盒", "M8×30", "紧固件", "晋亿", "20", "32", "small", 0.9),
    ("外六角螺栓 M10×40 304不锈钢 50只/盒", "M10×40-304", "紧固件", "海盐", "40", "65", "small", 0.6),
    ("平垫 M8 100只/盒", "M8平垫", "紧固件", "海盐", "6", "12", "small", 1.4),
    ("弹垫 M10 100只/盒", "M10弹垫", "紧固件", "海盐", "8", "15", "small", 1.2),
    ("螺母 M12 100只/盒", "M12螺母", "紧固件", "海盐", "18", "30", "small", 1.1),
    ("自攻螺丝 M4×20 100只/盒", "M4×20", "紧固件", "海盐", "5", "10", "small", 1.0),
    ("膨胀螺栓 M10×80 20只/盒", "M10×80", "紧固件", "海盐", "18", "30", "small", 0.8),
    ("双头螺栓 M14×80 10只/盒", "M14×80", "紧固件", "晋亿", "45", "70", "small", 0.5),
    # 机油 / 润滑
    ("潍柴 CI-4 15W-40 柴油机油 4L", "CI-4 15W-40 4L", "机油/润滑", "潍柴", "95", "135", "small", 1.4),
    ("潍柴 CH-4 20W-50 柴油机油 4L", "CH-4 20W-50 4L", "机油/润滑", "潍柴", "80", "115", "small", 1.2),
    ("长城尊龙 T500 15W-40 4L", "T500 15W-40 4L", "机油/润滑", "长城", "110", "155", "small", 0.9),
    ("壳牌 Rimula R3 15W-40 4L", "R3 15W-40 4L", "机油/润滑", "壳牌", "150", "210", "small", 0.6),
    ("美孚黑霸王 15W-40 4L", "黑霸王 15W-40 4L", "机油/润滑", "美孚", "180", "250", "small", 0.4),
    ("长城 46# 抗磨液压油 18L", "46# 18L", "机油/润滑", "长城", "230", "310", "medium", 0.5),
    ("壳牌 46# 液压油 18L", "46# 18L", "机油/润滑", "壳牌", "300", "390", "medium", 0.3),
    ("长城 85W-90 齿轮油 4L", "85W-90 4L", "机油/润滑", "长城", "85", "120", "small", 0.5),
    ("潍柴 防冻液 -25℃ 9kg", "-25℃ 9kg", "机油/润滑", "潍柴", "55", "85", "small", 0.6),
    ("通用锂基脂 3# 15kg", "3# 15kg", "机油/润滑", "长城", "120", "170", "small", 0.4),
    # 轴承
    ("深沟球轴承 6205-2RS", "6205-2RS", "轴承", "哈轴", "10", "18", "small", 1.2),
    ("深沟球轴承 6206-2RS", "6206-2RS", "轴承", "哈轴", "14", "24", "small", 1.0),
    ("深沟球轴承 6305-2RS", "6305-2RS", "轴承", "洛轴", "20", "32", "small", 0.9),
    ("深沟球轴承 6308-2RS", "6308-2RS", "轴承", "洛轴", "40", "62", "small", 0.6),
    ("深沟球轴承 6205-2RS", "6205-2RS", "轴承", "SKF", "45", "70", "small", 0.4),
    ("深沟球轴承 6305-2RS", "6305-2RS", "轴承", "SKF", "85", "125", "medium", 0.25),
    ("深沟球轴承 6206-2RS", "6206-2RS", "轴承", "NSK", "38", "58", "small", 0.35),
    ("外球面轴承 UC206", "UC206", "轴承", "哈轴", "25", "40", "small", 0.6),
    ("外球面轴承 UC208", "UC208", "轴承", "哈轴", "40", "62", "small", 0.45),
    ("圆锥滚子轴承 32208", "32208", "轴承", "洛轴", "30", "48", "small", 0.5),
    ("推力球轴承 51105", "51105", "轴承", "哈轴", "18", "30", "small", 0.4),
    ("深沟球轴承 6204-2RS", "6204-2RS", "轴承", "洛轴", "8", "15", "small", 0.8),
    # 滤清器
    ("机油滤清器 JX0810", "JX0810", "滤清器", "潍柴", "15", "25", "small", 1.3),
    ("柴油滤清器 1000428205", "1000428205", "滤清器", "潍柴", "30", "48", "small", 1.2),
    ("空气滤清器 K2640", "K2640", "滤清器", "潍柴", "60", "95", "small", 0.8),
    ("机油滤清器 JX1008", "JX1008", "滤清器", "东方红", "18", "30", "small", 1.0),
    ("柴油滤清器 C0710", "C0710", "滤清器", "东方红", "25", "40", "small", 0.9),
    ("机油滤清器 JX1023", "JX1023", "滤清器", "玉柴", "20", "34", "small", 0.8),
    ("液压滤芯 RE45864", "RE45864", "滤清器", "约翰迪尔", "120", "180", "medium", 0.3),
    ("空气滤芯 AT171854", "AT171854", "滤清器", "约翰迪尔", "150", "220", "medium", 0.25),
    ("柴油滤芯 15221-43170", "15221-43170", "滤清器", "久保田", "45", "70", "small", 0.4),
    ("液压油滤芯 雷沃", "雷沃液压滤", "滤清器", "雷沃", "55", "85", "small", 0.5),
    ("柴油预滤器 通用", "通用预滤器", "滤清器", "通用", "35", "55", "small", 0.6),
    ("燃油水分离器 潍柴", "燃油水分离器", "滤清器", "潍柴", "65", "100", "small", 0.5),
    # 刀片 / 农机具
    ("收割机刀片 久保田", "久保田刀片", "刀片/农机具", "久保田", "18", "30", "small", 0.9),
    ("收割机刀片 沃得", "沃得刀片", "刀片/农机具", "沃得", "16", "28", "small", 0.9),
    ("收割机刀片 雷沃", "雷沃刀片", "刀片/农机具", "雷沃", "17", "29", "small", 0.8),
    ("收割机刀片 约翰迪尔", "约翰迪尔刀片", "刀片/农机具", "约翰迪尔", "35", "55", "small", 0.4),
    ("旋耕刀 IT245 65Mn", "IT245", "刀片/农机具", "豪丰", "32", "46.5", "small", 1.0),
    ("旋耕刀 IT225 65Mn", "IT225", "刀片/农机具", "豪丰", "28", "42", "small", 0.8),
    ("犁刀片 65Mn", "犁刀片", "刀片/农机具", "通用", "25", "40", "small", 0.6),
    ("割草机刀片", "割草刀片", "刀片/农机具", "通用", "20", "35", "small", 0.4),
    ("链条 10A-1", "10A-1", "刀片/农机具", "通用", "45", "70", "small", 0.4),
    ("链轮 10A-1 20齿", "10A-1-20T", "刀片/农机具", "通用", "35", "55", "small", 0.35),
    # 液压
    ("液压油缸 3200 农用", "3200", "液压件", "约翰迪尔", "680", "980", "large", 0.2),
    ("液压油缸 4000 农用", "4000", "液压件", "约翰迪尔", "900", "1300", "large", 0.12),
    ("液压油管 2米 1/2寸", "2m-1/2", "液压件", "通用", "25", "40", "small", 0.7),
    ("液压油管 3米 3/4寸", "3m-3/4", "液压件", "通用", "45", "70", "small", 0.5),
    ("油封 35×55×8", "35×55×8", "液压件", "通用", "5", "10", "small", 0.9),
    ("油封 40×60×10", "40×60×10", "液压件", "通用", "6", "12", "small", 0.8),
    ("快速接头 1/2寸", "1/2寸", "液压件", "通用", "18", "30", "small", 0.6),
    ("液压齿轮泵", "齿轮泵", "液压件", "通用", "380", "550", "large", 0.25),
    ("液压多路阀 分配器", "多路阀", "液压件", "通用", "450", "650", "large", 0.2),
    # 电器
    ("拖拉机前照灯 12V LED", "12V LED", "电器/灯具", "福田", "35", "65", "small", 0.7),
    ("收割机工作灯 24V", "24V 工作灯", "电器/灯具", "通用", "30", "55", "small", 0.6),
    ("启动机 12V", "12V 启动机", "电器/灯具", "常柴", "420", "620", "large", 0.25),
    ("发电机 14V", "14V 发电机", "电器/灯具", "常柴", "380", "560", "large", 0.2),
    ("电瓶 12V 80Ah", "12V 80Ah", "电器/灯具", "骆驼", "420", "580", "large", 0.25),
    ("继电器 12V", "12V 继电器", "电器/灯具", "通用", "15", "28", "small", 0.8),
    ("拖拉机线束", "拖拉机线束", "电器/灯具", "通用", "55", "90", "small", 0.3),
    # 制动 / 传动
    ("三轮车刹车片", "三轮车刹车片", "制动/传动", "时风", "12", "25", "small", 0.9),
    ("拖拉机刹车片", "拖拉机刹车片", "制动/传动", "东方红", "25", "45", "small", 0.6),
    ("离合器片 东风", "东风离合器片", "制动/传动", "东风", "120", "180", "medium", 0.4),
    ("离合器压盘 东风", "东风压盘", "制动/传动", "东风", "280", "420", "large", 0.2),
    ("传动轴万向节", "万向节", "制动/传动", "通用", "65", "110", "small", 0.5),
    ("十字轴", "十字轴", "制动/传动", "通用", "35", "60", "small", 0.5),
    ("半轴 拖拉机", "半轴", "制动/传动", "通用", "180", "260", "medium", 0.2),
    # 植保
    ("植保机喷头 AG-01", "AG-01", "植保配件", "大疆", "12", "25", "small", 0.8),
    ("扇形喷头 110°", "110°", "植保配件", "大疆", "5", "12", "small", 1.0),
    ("喷杆 2米", "2米喷杆", "植保配件", "大疆", "45", "75", "small", 0.4),
    ("隔膜泵 12V", "12V 隔膜泵", "植保配件", "大疆", "120", "180", "medium", 0.3),
    ("植保过滤网", "过滤网", "植保配件", "大疆", "8", "15", "small", 0.6),
    # 轮胎
    ("人字胎 6.00-12", "6.00-12", "轮胎", "青岛橡六", "180", "260", "medium", 0.3),
    ("人字胎 6.50-16", "6.50-16", "轮胎", "青岛橡六", "260", "380", "medium", 0.25),
    ("人字胎 7.50-16", "7.50-16", "轮胎", "青岛橡六", "360", "520", "large", 0.2),
    ("人字胎 4.00-12", "4.00-12", "轮胎", "青岛橡六", "120", "180", "medium", 0.35),
    # 发动机件
    ("柴油机缸套 CC-195", "CC-195", "发动机件", "常柴", "55", "110", "small", 0.4),
    ("活塞环 CC-195", "CC-195", "发动机件", "常柴", "35", "65", "small", 0.35),
    ("气门室盖垫 CC-195", "CC-195", "发动机件", "常柴", "15", "28", "small", 0.4),
    ("水泵水封", "水泵水封", "发动机件", "常柴", "8", "15", "small", 0.4),
    ("空气滤芯 通用", "通用空滤", "发动机件", "通用", "20", "35", "small", 0.6),
]


def build_products() -> list[Product]:
    products: list[Product] = []
    for index, row in enumerate(RAW_PRODUCTS, start=1):
        name, model, category, brand, cost_s, retail_s, kind, weight = row
        cost = Decimal(cost_s)
        retail = Decimal(retail_s)
        if retail <= cost:
            raise ValueError(f"零售价必须高于成本：{name}")
        initial, reorder, replenish, max_qty = _profile(cost, kind)
        products.append(
            Product(
                id=index,
                name=name,
                model=model,
                category=category,
                brand=brand,
                cost=cost,
                retail=retail,
                kind=kind,
                weight=weight,
                initial_stock=initial,
                reorder=reorder,
                replenish=replenish,
                max_qty=max_qty,
            )
        )
    return products


SUPPLIER_DATA = [
    ("潍坊潍柴动力配件有限公司", "0536-8234567"),
    ("常州东风农机配件厂", "0519-86681234"),
    ("山东三力士传动带销售处", "0531-88997654"),
    ("哈尔滨轴承集团华东销售部", "0451-82651188"),
    ("浙江三维橡胶制品有限公司", "0576-84031888"),
    ("晋亿实业紧固件经销部", "0573-84125678"),
    ("河北海盐紧固件厂", "0317-6283456"),
    ("洛阳轴承销售有限公司", "0379-64881234"),
    ("江苏常柴柴油机配件公司", "0519-85226789"),
    ("重庆大江动力设备有限公司", "023-67123456"),
    ("上海盖茨传动带代理商", "021-58912345"),
    ("约翰迪尔农机配件经销处", "010-67891234"),
    ("久保田农机配件中心", "021-67892345"),
    ("雷沃农机配件供应站", "0536-7654321"),
    ("长城润滑油农机渠道商", "010-84561234"),
    ("壳牌农机润滑油经销商", "021-62345678"),
    ("浙江植保机械配件厂", "0576-83214567"),
    ("山东时风集团配件部", "0635-8321456"),
    ("河南新乡农机具厂", "0373-3021456"),
    ("青岛橡六轮胎销售处", "0532-85671234"),
    ("安徽全柴动力配件公司", "0550-5012345"),
    ("江苏沃得农机配件中心", "0511-86891234"),
]

CUSTOMER_DATA = [
    # 客户全部按当地农机门市、维修部、配件店的常见叫法命名；
    # 字号、姓名、行政前缀随机组合，不套固定模板；均为演示用虚构客户。
    ("杞县邢口镇利民农机维修部", "0371-31925368"),
    ("李长海农机维修部", "19900003285"),
    ("杞县老李农机配件门市部", "0371-24787919"),
    ("邢口镇王守田农机配件店", "19900004468"),
    ("杞县张保全农机维修部", "19900006144"),
    ("老周农机维修部", "0371-88442858"),
    ("杞县邢口镇刘新社农机配件门市部", "19900009766"),
    ("陈留柱农机修理部", "19900005324"),
    ("杞县邢口镇建新农机维修中心", "0371-32028512"),
    ("杞县冷屯村杨运来农机维修部", "19900008208"),
    ("王德顺农机配件经营部", "19900008019"),
    ("邢口镇孙保平农机修理铺", "19900004389"),
    ("杞县马金坡农机配件门市部", "19900004658"),
    ("周玉堂农机维修站", "19900001050"),
    ("杞县邢口镇朱广利农机配件商行", "19900003735"),
    ("傅集镇建力农机配件店", "0371-84636278"),
    ("通许县高存良农机配件门市部", "19900007348"),
    ("杞县宗店乡金穗农机门市部", "0371-31843943"),
    ("开封市祥符区郭进才农机维修部", "19900002444"),
    ("板木乡顺达农机修理部", "0371-25260452"),
    ("杞县何秀兰农机配件店", "19900009585"),
    ("杞县苏木乡宏发农机配件门市部", "0371-21102831"),
    ("开封市祥符区丰农农业机械销售有限公司", "0371-29162899"),
    ("湖岗乡禾丰农机维修部", "0371-84057962"),
    ("尉氏县罗文周农机维修部", "19900006178"),
    ("杞县高阳镇沃土农机配件店", "0371-39665140"),
    ("通许县永兴农机维修部", "0371-85747904"),
    ("杞县邢口镇袁清合农机维修中心", "19900001919"),
    ("尉氏县顺农农机配件门市部", "0371-34634718"),
    ("杞县兴田农业机械有限公司", "0371-86542604"),
]


def build_partners() -> list[Partner]:
    partners: list[Partner] = []
    partner_id = 1
    for name, phone in SUPPLIER_DATA:
        partners.append(Partner(partner_id, name, "supplier", phone))
        partner_id += 1
    for name, phone in CUSTOMER_DATA:
        partners.append(Partner(partner_id, name, "customer", phone))
        partner_id += 1
    return partners


PRODUCTS = build_products()
PARTNERS = build_partners()
SUPPLIERS = [partner for partner in PARTNERS if partner.type == "supplier"]
CUSTOMERS = [partner for partner in PARTNERS if partner.type == "customer"]

IP_POOL = [
    "192.168.1.20",
    "192.168.1.21",
    "192.168.1.22",
    "10.0.0.15",
    "10.0.0.16",
    "10.0.0.18",
]
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Edg/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.1 Mobile/15E148 Safari/604.1",
]

HOLIDAY_WINDOWS = [
    (date(2023, 1, 21), date(2023, 1, 27)),
    (date(2024, 2, 9), date(2024, 2, 15)),
    (date(2025, 1, 28), date(2025, 2, 3)),
    (date(2026, 2, 16), date(2026, 2, 22)),
]
MONTH_FACTORS = {
    1: 0.72,
    2: 0.55,
    3: 1.28,
    4: 1.35,
    5: 1.28,
    6: 0.95,
    7: 0.85,
    8: 0.98,
    9: 1.45,
    10: 1.5,
    11: 1.05,
    12: 0.75,
}


def daily_target(day: date) -> Decimal:
    factor = Decimal(str(MONTH_FACTORS[day.month]))
    if day.weekday() == 6:
        factor *= Decimal("0.72")
    elif day.weekday() == 5:
        factor *= Decimal("1.04")

    for start, end in HOLIDAY_WINDOWS:
        if start <= day <= end:
            factor *= Decimal("0.18")
            break

    noise = Decimal(str(RNG.uniform(0.72, 1.3)))
    target = Decimal("1150") * factor * noise
    target = min(max(target, Decimal("350")), Decimal("3200"))
    return money(target)


def weighted_operator() -> str:
    keys = list(USER_WEIGHTS)
    weights = list(USER_WEIGHTS.values())
    return RNG.choices(keys, weights=weights, k=1)[0]


def actual_sale_price(product: Product) -> Decimal:
    if product.kind == "machinery":
        discount = RNG.uniform(0.94, 1.0)
    elif product.kind in {"large", "medium"}:
        discount = RNG.uniform(0.92, 1.0)
    else:
        discount = RNG.choice([1.0, 1.0, 0.98, 0.95, 0.92])

    price = product.retail * Decimal(str(discount))
    floor = product.cost * Decimal("1.08")
    return money(max(price, floor))


def actual_purchase_price(product: Product) -> Decimal:
    return money(product.cost * Decimal(str(RNG.uniform(0.96, 1.04))))


class Dataset:
    def __init__(self) -> None:
        self.purchase_orders: list[dict[str, Any]] = []
        self.purchase_items: list[dict[str, Any]] = []
        self.sale_orders: list[dict[str, Any]] = []
        self.sale_items: list[dict[str, Any]] = []
        self.inventory_logs: list[dict[str, Any]] = []
        self.audit_logs: list[dict[str, Any]] = []
        self.stock: dict[int, int] = {product.id: product.initial_stock for product in PRODUCTS}
        self.purchase_order_id = 0
        self.purchase_item_id = 0
        self.sale_order_id = 0
        self.sale_item_id = 0
        self.inventory_log_id = 0
        self.audit_id = 0
        self.day_sequences: dict[tuple[str, date], int] = {}
        self.total_revenue = Decimal("0.00")
        self.total_cost = Decimal("0.00")
        self.total_purchase = Decimal("0.00")
        self.month_revenue: dict[str, Decimal] = {}

    def add_inventory_log(
        self,
        *,
        part_id: int,
        change_type: str,
        change_qty: int,
        before_stock: int,
        after_stock: int,
        operator: str,
        created_at: datetime,
        remark: str,
    ) -> None:
        self.inventory_log_id += 1
        self.inventory_logs.append(
            {
                "id": self.inventory_log_id,
                "part_id": part_id,
                "change_type": change_type,
                "change_qty": change_qty,
                "before_stock": before_stock,
                "after_stock": after_stock,
                "operator": operator,
                "remark": remark,
                "created_at": created_at,
            }
        )

    def add_audit(
        self,
        *,
        user_key: str | None,
        username: str,
        role: str,
        action: str,
        module: str,
        created_at: datetime,
        resource_type: str | None = None,
        resource_id: int | None = None,
        method: str | None = None,
        path: str | None = None,
        status_code: int = 200,
        success: bool = True,
        error_code: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self.audit_id += 1
        self.audit_logs.append(
            {
                "id": self.audit_id,
                "user_key": user_key,
                "username": username,
                "role": role,
                "action": action,
                "module": module,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "method": method,
                "path": path,
                "status_code": status_code,
                "success": success,
                "error_code": error_code,
                "detail": detail,
                "ip": RNG.choice(IP_POOL),
                "user_agent": RNG.choice(USER_AGENTS),
                "request_id": f"{RNG.getrandbits(64):016x}",
                "duration_ms": RNG.randint(25, 680),
                "created_at": created_at,
            }
        )


def next_order_no(dataset: Dataset, prefix: str, day: date) -> str:
    key = (prefix, day)
    dataset.day_sequences[key] = dataset.day_sequences.get(key, 0) + 1
    return f"{prefix}{day:%Y%m%d}{dataset.day_sequences[key]:04d}"


def create_purchase_order(
    dataset: Dataset,
    *,
    day: date,
    items: list[tuple[Product, int]],
    operator: str,
    created_at: datetime,
    remark: str,
) -> None:
    partner = RNG.choice(SUPPLIERS)
    dataset.purchase_order_id += 1
    order_id = dataset.purchase_order_id
    order_no = next_order_no(dataset, "PO", day)
    total = Decimal("0.00")
    item_rows: list[dict[str, Any]] = []

    for product, quantity in items:
        price = actual_purchase_price(product)
        total += price * quantity
        dataset.purchase_item_id += 1
        item_rows.append(
            {
                "id": dataset.purchase_item_id,
                "order_id": order_id,
                "part_id": product.id,
                "quantity": quantity,
                "price": price,
            }
        )

    total = money(total)
    dataset.purchase_orders.append(
        {
            "id": order_id,
            "order_no": order_no,
            "partner_id": partner.id,
            "total_amount": total,
            "status": "completed",
            "operator": operator,
            "remark": remark,
            "created_at": created_at,
        }
    )
    dataset.total_purchase += total

    for index, item in enumerate(item_rows):
        product = next(product for product in PRODUCTS if product.id == item["part_id"])
        before = dataset.stock[product.id]
        dataset.stock[product.id] += item["quantity"]
        dataset.add_inventory_log(
            part_id=product.id,
            change_type="in",
            change_qty=item["quantity"],
            before_stock=before,
            after_stock=dataset.stock[product.id],
            operator=operator,
            created_at=created_at + timedelta(seconds=index + 1),
            remark=f"采购入库 {order_no}",
        )
        dataset.purchase_items.append(item)

    dataset.add_audit(
        user_key=operator,
        username=operator,
        role=USER_DEFS[operator]["role"],
        action="purchase.inbound",
        module="purchases",
        created_at=created_at + timedelta(seconds=3),
        resource_type="purchase_order",
        resource_id=order_id,
        method="POST",
        path="/api/v1/purchases/inbound",
        status_code=201,
        detail={
            "order_no": order_no,
            "partner_id": partner.id,
            "partner_name": partner.name,
            "total_amount": format(total, "f"),
            "item_count": len(item_rows),
        },
    )


def create_sale_order(
    dataset: Dataset,
    *,
    day: date,
    items: list[tuple[Product, int, Decimal]],
    operator: str,
    created_at: datetime,
    remark: str,
) -> Decimal:
    partner = RNG.choice(CUSTOMERS)
    dataset.sale_order_id += 1
    order_id = dataset.sale_order_id
    order_no = next_order_no(dataset, "SO", day)
    total = Decimal("0.00")
    item_rows: list[dict[str, Any]] = []

    for product, quantity, price in items:
        total += price * quantity
        dataset.sale_item_id += 1
        item_rows.append(
            {
                "id": dataset.sale_item_id,
                "order_id": order_id,
                "part_id": product.id,
                "quantity": quantity,
                "price": price,
            }
        )

    total = money(total)
    dataset.sale_orders.append(
        {
            "id": order_id,
            "order_no": order_no,
            "partner_id": partner.id,
            "total_amount": total,
            "status": "completed",
            "operator": operator,
            "remark": remark,
            "created_at": created_at,
        }
    )
    dataset.total_revenue += total
    month_key = f"{day.year:04d}-{day.month:02d}"
    dataset.month_revenue[month_key] = dataset.month_revenue.get(month_key, Decimal("0.00")) + total

    for index, (product, quantity, _) in enumerate(items):
        before = dataset.stock[product.id]
        dataset.stock[product.id] -= quantity
        dataset.add_inventory_log(
            part_id=product.id,
            change_type="out",
            change_qty=-quantity,
            before_stock=before,
            after_stock=dataset.stock[product.id],
            operator=operator,
            created_at=created_at + timedelta(seconds=index + 1),
            remark=f"销售出库 {order_no}",
        )
        dataset.sale_items.append(item_rows[index])
        dataset.total_cost += product.cost * quantity

    dataset.add_audit(
        user_key=operator,
        username=operator,
        role=USER_DEFS[operator]["role"],
        action="sale.outbound",
        module="sales",
        created_at=created_at + timedelta(seconds=3),
        resource_type="sale_order",
        resource_id=order_id,
        method="POST",
        path="/api/v1/sales/outbound",
        status_code=201,
        detail={
            "order_no": order_no,
            "partner_id": partner.id,
            "partner_name": partner.name,
            "total_amount": format(total, "f"),
            "items": [
                {
                    "part_id": product.id,
                    "part_name": product.name,
                    "quantity": quantity,
                    "price": format(price, "f"),
                }
                for product, quantity, price in items
            ],
        },
    )
    return total


def build_dataset() -> Dataset:
    dataset = Dataset()

    # 期初库存
    initial_time = local_dt(START_DAY, 8, 0, 0)
    for product in PRODUCTS:
        dataset.add_inventory_log(
            part_id=product.id,
            change_type="check",
            change_qty=product.initial_stock,
            before_stock=0,
            after_stock=product.initial_stock,
            operator="admin",
            created_at=initial_time,
            remark="期初库存",
        )

    day = START_DAY
    while day <= END_DAY:
        target = daily_target(day)
        # 先补货，再销售
        # 补货策略：低库存优先 + 动销较快的商品定期回补，接近真实门店采购节奏
        restock_candidates = sorted(
            (
                product
                for product in PRODUCTS
                if dataset.stock[product.id] <= product.reorder
                or (
                    product.weight >= 0.25
                    and dataset.stock[product.id] < product.initial_stock * 0.9
                )
            ),
            key=lambda product: dataset.stock[product.id] / max(1, product.initial_stock),
        )
        if restock_candidates:
            chunks = [restock_candidates[:8]]
            if len(restock_candidates) > 8:
                chunks.append(restock_candidates[8:16])
            for index, chunk in enumerate(chunks):
                # 采购单通常包含多个 SKU：候选不足时补充动销较快的商品
                if len(chunk) < 4:
                    extra = [
                        product
                        for product in PRODUCTS
                        if product not in chunk
                        and product.weight >= 0.3
                        and dataset.stock[product.id] < product.initial_stock * 1.15
                    ]
                    extra.sort(
                        key=lambda product: dataset.stock[product.id]
                        / max(1, product.initial_stock)
                    )
                    chunk = list(chunk) + extra[: 4 - len(chunk)]
                purchase_time = local_dt(day, 8, 10 + index * 15, RNG.randint(0, 20))
                purchase_items: list[tuple[Product, int]] = []
                for product in chunk:
                    if product.kind == "machinery":
                        quantity = 1
                    elif product.kind == "large":
                        quantity = RNG.randint(1, 3)
                    elif product.kind == "medium":
                        quantity = RNG.randint(5, 20)
                    else:
                        quantity = RNG.randint(30, 120)

                    if dataset.stock[product.id] <= product.reorder:
                        quantity = max(quantity, product.replenish)
                    purchase_items.append((product, quantity))
                create_purchase_order(
                    dataset,
                    day=day,
                    items=purchase_items,
                    operator=weighted_operator(),
                    created_at=purchase_time,
                    remark=RNG.choice(["常规补货", "旺季备货", "紧急补货"]),
                )

        revenue = Decimal("0.00")
        order_count = 0
        cursor = local_dt(day, 8, 50, 0)
        actors: set[str] = set()

        while revenue < target and order_count < 28:
            if cursor > local_dt(day, 18, 25, 0):
                break

            item_count = RNG.choices([1, 2, 3, 4], weights=[0.55, 0.3, 0.12, 0.03], k=1)[0]
            chosen: list[tuple[Product, int, Decimal]] = []
            used_ids: set[int] = set()

            for _ in range(item_count):
                available = [
                    product
                    for product in PRODUCTS
                    if dataset.stock[product.id] > 0 and product.id not in used_ids
                ]
                if not available:
                    break

                product = RNG.choices(
                    available,
                    weights=[product.weight for product in available],
                    k=1,
                )[0]

                remaining = target - revenue
                if (
                    revenue > 0
                    and product.retail > Decimal("500")
                    and product.retail > max(Decimal("700"), remaining * Decimal("1.6"))
                ):
                    cheap = [item for item in available if item.retail <= Decimal("300")]
                    if cheap:
                        product = RNG.choices(
                            cheap, weights=[item.weight for item in cheap], k=1
                        )[0]
                    else:
                        continue

                max_qty = min(product.max_qty, dataset.stock[product.id])
                if max_qty <= 0:
                    continue
                if product.kind == "machinery":
                    quantity = 1
                elif product.kind == "large":
                    quantity = min(max_qty, RNG.choices([1, 2], weights=[0.7, 0.3], k=1)[0])
                elif product.kind == "medium":
                    quantity = min(max_qty, RNG.choices([1, 2, 3], weights=[0.5, 0.35, 0.15], k=1)[0])
                else:
                    quantity = min(
                        max_qty,
                        RNG.choices([1, 2, 3, 4, 5], weights=[0.35, 0.3, 0.18, 0.1, 0.07], k=1)[0],
                    )

                chosen.append((product, quantity, actual_sale_price(product)))
                used_ids.add(product.id)

            if not chosen:
                break

            order_total = sum(price * quantity for _, quantity, price in chosen)

            operator = weighted_operator()
            actors.add(operator)
            time_cursor = cursor
            create_sale_order(
                dataset,
                day=day,
                items=chosen,
                operator=operator,
                created_at=time_cursor,
                remark=RNG.choice(["门市销售", "老客户供货", "维修配件", "田间急送"]),
            )
            revenue += order_total
            order_count += 1
            cursor = cursor + timedelta(minutes=RNG.randint(12, 42))
            if cursor > local_dt(day, 18, 30, 0):
                break

        if not actors:
            actors = {"staff"}

        # 登录/退出审计
        for operator in sorted(actors):
            login_time = local_dt(day, 8, 5, 0) + timedelta(
                minutes=RNG.randint(0, 25), seconds=RNG.randint(0, 59)
            )
            dataset.add_audit(
                user_key=operator,
                username=operator,
                role=USER_DEFS[operator]["role"],
                action="auth.login",
                module="auth",
                created_at=login_time,
                method="POST",
                path="/api/v1/auth/login",
                status_code=200,
                detail={
                    "username": operator,
                    "role": USER_DEFS[operator]["role"],
                    "result": "success",
                },
            )
            logout_time = local_dt(day, 18, 35, 0) + timedelta(
                minutes=RNG.randint(0, 30), seconds=RNG.randint(0, 59)
            )
            dataset.add_audit(
                user_key=operator,
                username=operator,
                role=USER_DEFS[operator]["role"],
                action="auth.logout",
                module="auth",
                created_at=logout_time,
                method="POST",
                path="/api/v1/auth/logout",
                status_code=200,
                detail={"username": operator},
            )

        if RNG.random() < 0.035:
            failed_user = RNG.choice(["admin", "staff", "staff01", "unknown"])
            dataset.add_audit(
                user_key=failed_user if failed_user != "unknown" else None,
                username=failed_user,
                role=USER_DEFS.get(failed_user, {}).get("role", ""),
                action="auth.login_failed",
                module="auth",
                created_at=local_dt(day, 8, RNG.randint(0, 40), RNG.randint(0, 59)),
                method="POST",
                path="/api/v1/auth/login",
                status_code=401,
                success=False,
                error_code="INVALID_CREDENTIALS",
                detail={"username": failed_user, "reason": "invalid_credentials"},
            )

        if day.day % 11 == 0:
            product = RNG.choice(PRODUCTS)
            old_price = product.retail
            new_price = money(old_price * Decimal(str(RNG.uniform(0.96, 1.04))))
            dataset.add_audit(
                user_key="admin",
                username="admin",
                role="boss",
                action="part.update",
                module="parts",
                created_at=local_dt(day, 15, RNG.randint(0, 45), RNG.randint(0, 59)),
                resource_type="part",
                resource_id=product.id,
                method="PUT",
                path=f"/api/v1/parts/{product.id}",
                status_code=200,
                detail={
                    "name": product.name,
                    "changed": {"sale_price": format(new_price, "f")},
                    "before": {"sale_price": format(old_price, "f")},
                },
            )

        if day.weekday() == 0:
            month_key = f"{day.year:04d}-{day.month:02d}"
            dataset.add_audit(
                user_key="admin",
                username="admin",
                role="boss",
                action="dashboard.view",
                module="dashboard",
                created_at=local_dt(day, 19, RNG.randint(0, 30), RNG.randint(0, 59)),
                method="GET",
                path="/api/v1/dashboard",
                status_code=200,
                detail={
                    "today_sales_amount": format(revenue, "f"),
                    "month_sales_amount": format(
                        dataset.month_revenue.get(month_key, Decimal("0.00")), "f"
                    ),
                },
            )

        if day.day == 1:
            dataset.add_audit(
                user_key="admin",
                username="admin",
                role="boss",
                action="audit.view",
                module="audit",
                created_at=local_dt(day, 9, 30, RNG.randint(0, 59)),
                method="GET",
                path="/api/v1/audit/logs",
                status_code=200,
                detail={"page": 1, "page_size": 20, "action": None},
            )

        if (day - START_DAY).days % 37 == 0:
            product = RNG.choice(PRODUCTS)
            dataset.add_audit(
                user_key="staff",
                username="staff",
                role="employee",
                action="sale.outbound",
                module="sales",
                created_at=local_dt(day, 16, RNG.randint(0, 40), RNG.randint(0, 59)),
                method="POST",
                path="/api/v1/sales/outbound",
                status_code=409,
                success=False,
                error_code="INSUFFICIENT_STOCK",
                detail={
                    "request": {
                        "customer_id": RNG.choice(CUSTOMERS).id,
                        "part_id": product.id,
                        "quantity": dataset.stock[product.id] + RNG.randint(2, 30),
                    },
                    "message": "库存不足，销售单已回滚",
                },
            )

        if (day - START_DAY).days % 53 == 0:
            product = RNG.choice(PRODUCTS)
            dataset.add_audit(
                user_key="staff",
                username="staff",
                role="employee",
                action="sale.outbound",
                module="sales",
                created_at=local_dt(day, 17, RNG.randint(0, 30), RNG.randint(0, 59)),
                method="POST",
                path="/api/v1/sales/outbound",
                status_code=403,
                success=False,
                error_code="PRICE_OVERRIDE_FORBIDDEN",
                detail={
                    "request": {
                        "customer_id": RNG.choice(CUSTOMERS).id,
                        "part_id": product.id,
                        "quantity": 1,
                        "price": format(money(product.retail * Decimal("0.6")), "f"),
                    },
                    "message": "仅老板可以调整销售成交价",
                },
            )

        day += timedelta(days=1)

    return dataset


def collect_stats(dataset: Dataset) -> dict[str, Any]:
    sale_items_count = len(dataset.sale_items)
    purchase_items_count = len(dataset.purchase_items)
    gross_profit = dataset.total_revenue - dataset.total_cost
    gross_margin = (
        (gross_profit / dataset.total_revenue * 100).quantize(Decimal("0.01"))
        if dataset.total_revenue
        else Decimal("0")
    )
    average_month_revenue = (
        dataset.total_revenue / max(1, len(dataset.month_revenue))
    ).quantize(MONEY) if dataset.total_revenue else Decimal("0")

    return {
        "period": {
            "start_local": START_DAY.isoformat(),
            "end_local": END_DAY.isoformat(),
            "days": (END_DAY - START_DAY).days + 1,
            "timezone": str(TZ),
            "database_time": "UTC",
        },
        "counts": {
            "products": len(PRODUCTS),
            "partners": len(PARTNERS),
            "suppliers": len(SUPPLIERS),
            "customers": len(CUSTOMERS),
            "purchase_orders": len(dataset.purchase_orders),
            "purchase_items": purchase_items_count,
            "sale_orders": len(dataset.sale_orders),
            "sale_items": sale_items_count,
            "inventory_logs": len(dataset.inventory_logs),
            "audit_logs": len(dataset.audit_logs),
        },
        "money": {
            "total_sales": format(dataset.total_revenue, "f"),
            "total_purchase": format(dataset.total_purchase, "f"),
            "cost_of_goods_sold": format(dataset.total_cost, "f"),
            "gross_profit": format(gross_profit, "f"),
            "gross_margin_percent": format(gross_margin, "f"),
            "average_month_sales": format(average_month_revenue, "f"),
            "average_daily_orders": round(len(dataset.sale_orders) / ((END_DAY - START_DAY).days + 1), 2),
        },
        "final_stock": {
            str(product.id): dataset.stock[product.id] for product in PRODUCTS
        },
    }


def _row(values: list[str]) -> str:
    return "(" + ", ".join(values) + ")"


def _write_insert(
    handle: Any,
    table: str,
    columns: list[str],
    rows: list[list[str]],
    batch_size: int = 200,
) -> None:
    if not rows:
        return
    column_sql = ", ".join(columns)
    for offset in range(0, len(rows), batch_size):
        batch = rows[offset : offset + batch_size]
        handle.write(f"INSERT INTO {table} ({column_sql}) VALUES\n")
        handle.write(",\n".join(_row(row) for row in batch))
        handle.write(";\n")


def write_sql(dataset: Dataset, stats: dict[str, Any]) -> None:
    SQL_DIR.mkdir(exist_ok=True)

    user_hashes = {
        key: hash_password(value["password"]) for key, value in USER_DEFS.items()
    }

    with SQL_PATH.open("w", encoding="utf-8") as sql:
        sql.write("-- ============================================================\n")
        sql.write("-- 农机配件进销存 ERP - 2022-09-12 ~ 2026-10-01 历史演示数据\n")
        sql.write("-- 生成器：scripts/generate_historical_sql.py\n")
        sql.write("-- 目标数据库：MySQL 8.0（DBeaver 直接执行本文件）\n")
        sql.write("--\n")
        sql.write("-- 前置条件：\n")
        sql.write("--   1. 已执行 `alembic upgrade head`，audit_logs 表存在；\n")
        sql.write("--   2. 已备份数据库；\n")
        sql.write("--   3. 脚本会清空 parts/partners/orders/items/inventory_logs/audit_logs，\n")
        sql.write("--      但保留 users 表及现有账号密码；缺失时创建演示账号。\n")
        sql.write("--\n")
        sql.write("-- 时间说明：数据库存 UTC，已从 Asia/Shanghai 转换；本地查看需 +8 小时。\n")
        sql.write("-- 金额说明：parts.purchase_price=参考进货价，parts.sale_price=建议零售价；\n")
        sql.write("--           sale_items.price=实际成交单价，sale_orders.total_amount=订单实收总额。\n")
        sql.write("-- ============================================================\n\n")
        sql.write("SET NAMES utf8mb4;\n")
        sql.write("SET FOREIGN_KEY_CHECKS = 0;\n")
        sql.write("SET UNIQUE_CHECKS = 0;\n\n")

        sql.write("-- 清空业务数据（保留用户）\n")
        for table in (
            "audit_logs",
            "inventory_logs",
            "sale_items",
            "purchase_items",
            "sale_orders",
            "purchase_orders",
            "parts",
            "partners",
        ):
            sql.write(f"TRUNCATE TABLE {table};\n")
        sql.write("\n")

        sql.write("-- 确保演示账号存在（不覆盖已有密码）\n")
        for username, definition in USER_DEFS.items():
            sql.write(
                "INSERT INTO users "
                "(username, password_hash, role, is_active, created_at, updated_at)\n"
                f"SELECT {sql_str(username)}, {sql_str(user_hashes[username])}, "
                f"{sql_str(definition['role'])}, 1, "
                "'2022-01-01 00:00:00', '2022-01-01 00:00:00'\n"
                f"WHERE NOT EXISTS (SELECT 1 FROM users WHERE username = {sql_str(username)});\n"
            )
        sql.write(
            "SET @admin_id := (SELECT id FROM users WHERE username = 'admin' LIMIT 1);\n"
        )
        sql.write(
            "SET @staff_id := (SELECT id FROM users WHERE username = 'staff' LIMIT 1);\n"
        )
        sql.write(
            "SET @staff01_id := "
            "(SELECT id FROM users WHERE username = 'staff01' LIMIT 1);\n\n"
        )

        sql.write("START TRANSACTION;\n\n")

        # 往来单位
        partner_rows: list[list[str]] = []
        for index, partner in enumerate(PARTNERS):
            created = local_dt(date(2021, 6, 1) + timedelta(days=index % 420), 9, 0, 0)
            partner_rows.append(
                [
                    str(partner.id),
                    sql_str(partner.name),
                    sql_str(partner.type),
                    sql_str(partner.phone),
                    sql_dt(created),
                    sql_dt(created),
                ]
            )
        _write_insert(
            sql,
            "partners",
            ["id", "name", "type", "phone", "created_at", "updated_at"],
            partner_rows,
            batch_size=100,
        )

        # 配件（stock 为仿真结束库存）
        part_rows: list[list[str]] = []
        for index, product in enumerate(PRODUCTS):
            created = local_dt(date(2021, 3, 1) + timedelta(days=index * 3 % 500), 10, 0, 0)
            part_rows.append(
                [
                    str(product.id),
                    sql_str(product.name),
                    sql_str(product.model),
                    sql_str(product.category),
                    sql_str(product.brand),
                    str(dataset.stock[product.id]),
                    str(product.reorder),
                    sql_num(product.cost),
                    sql_num(product.retail),
                    sql_dt(created),
                    sql_dt(created),
                ]
            )
        _write_insert(
            sql,
            "parts",
            [
                "id",
                "name",
                "model",
                "category",
                "brand",
                "stock",
                "safe_stock",
                "purchase_price",
                "sale_price",
                "created_at",
                "updated_at",
            ],
            part_rows,
            batch_size=100,
        )

        # 采购单 / 明细
        purchase_order_rows: list[list[str]] = []
        for order in dataset.purchase_orders:
            updated = order["created_at"] + timedelta(minutes=5)
            purchase_order_rows.append(
                [
                    str(order["id"]),
                    sql_str(order["order_no"]),
                    str(order["partner_id"]),
                    sql_num(order["total_amount"]),
                    sql_str(order["status"]),
                    f"@{order['operator']}_id",
                    sql_str(order["remark"]),
                    sql_dt(order["created_at"]),
                    sql_dt(updated),
                ]
            )
        _write_insert(
            sql,
            "purchase_orders",
            [
                "id",
                "order_no",
                "partner_id",
                "total_amount",
                "status",
                "operator_id",
                "remark",
                "created_at",
                "updated_at",
            ],
            purchase_order_rows,
        )

        purchase_item_rows = [
            [
                str(item["id"]),
                str(item["order_id"]),
                str(item["part_id"]),
                str(item["quantity"]),
                sql_num(item["price"]),
            ]
            for item in dataset.purchase_items
        ]
        _write_insert(
            sql,
            "purchase_items",
            ["id", "order_id", "part_id", "quantity", "price"],
            purchase_item_rows,
        )

        # 销售单 / 明细
        sale_order_rows: list[list[str]] = []
        for order in dataset.sale_orders:
            updated = order["created_at"] + timedelta(minutes=3)
            sale_order_rows.append(
                [
                    str(order["id"]),
                    sql_str(order["order_no"]),
                    str(order["partner_id"]),
                    sql_num(order["total_amount"]),
                    sql_str(order["status"]),
                    f"@{order['operator']}_id",
                    sql_str(order["remark"]),
                    sql_dt(order["created_at"]),
                    sql_dt(updated),
                ]
            )
        _write_insert(
            sql,
            "sale_orders",
            [
                "id",
                "order_no",
                "partner_id",
                "total_amount",
                "status",
                "operator_id",
                "remark",
                "created_at",
                "updated_at",
            ],
            sale_order_rows,
        )

        sale_item_rows = [
            [
                str(item["id"]),
                str(item["order_id"]),
                str(item["part_id"]),
                str(item["quantity"]),
                sql_num(item["price"]),
            ]
            for item in dataset.sale_items
        ]
        _write_insert(
            sql,
            "sale_items",
            ["id", "order_id", "part_id", "quantity", "price"],
            sale_item_rows,
        )

        # 库存流水
        inventory_rows = [
            [
                str(item["id"]),
                str(item["part_id"]),
                sql_str(item["change_type"]),
                str(item["change_qty"]),
                str(item["before_stock"]),
                str(item["after_stock"]),
                f"@{item['operator']}_id",
                sql_str(item["remark"]),
                sql_dt(item["created_at"]),
            ]
            for item in dataset.inventory_logs
        ]
        _write_insert(
            sql,
            "inventory_logs",
            [
                "id",
                "part_id",
                "change_type",
                "change_qty",
                "before_stock",
                "after_stock",
                "operator_id",
                "remark",
                "created_at",
            ],
            inventory_rows,
        )

        # 操作审计
        audit_rows: list[list[str]] = []
        for item in dataset.audit_logs:
            user_id = f"@{item['user_key']}_id" if item["user_key"] else "NULL"
            detail = (
                sql_str(
                    json.dumps(
                        item["detail"],
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                )
                if item["detail"] is not None
                else "NULL"
            )
            audit_rows.append(
                [
                    str(item["id"]),
                    user_id,
                    sql_str(item["username"]),
                    sql_str(item["role"]),
                    sql_str(item["action"]),
                    sql_str(item["module"]),
                    sql_str(item["resource_type"]),
                    str(item["resource_id"]) if item["resource_id"] is not None else "NULL",
                    sql_str(item["method"]),
                    sql_str(item["path"]),
                    str(item["status_code"]),
                    "1" if item["success"] else "0",
                    sql_str(item["error_code"]),
                    detail,
                    sql_str(item["ip"]),
                    sql_str(item["user_agent"]),
                    sql_str(item["request_id"]),
                    str(item["duration_ms"]),
                    sql_dt(item["created_at"]),
                ]
            )
        _write_insert(
            sql,
            "audit_logs",
            [
                "id",
                "user_id",
                "username",
                "role",
                "action",
                "module",
                "resource_type",
                "resource_id",
                "method",
                "path",
                "status_code",
                "success",
                "error_code",
                "detail",
                "ip",
                "user_agent",
                "request_id",
                "duration_ms",
                "created_at",
            ],
            audit_rows,
        )

        sql.write("\nCOMMIT;\n")
        sql.write("SET UNIQUE_CHECKS = 1;\n")
        sql.write("SET FOREIGN_KEY_CHECKS = 1;\n\n")
        sql.write("ANALYZE TABLE parts, partners, purchase_orders, purchase_items, ")
        sql.write("sale_orders, sale_items, inventory_logs, audit_logs;\n\n")
        sql.write("-- 导入后自检（可选，DBeaver 会显示结果）\n")
        sql.write("SELECT 'parts' AS table_name, COUNT(*) AS row_count FROM parts\n")
        sql.write("UNION ALL SELECT 'partners', COUNT(*) FROM partners\n")
        sql.write("UNION ALL SELECT 'purchase_orders', COUNT(*) FROM purchase_orders\n")
        sql.write("UNION ALL SELECT 'sale_orders', COUNT(*) FROM sale_orders\n")
        sql.write("UNION ALL SELECT 'sale_items', COUNT(*) FROM sale_items\n")
        sql.write("UNION ALL SELECT 'inventory_logs', COUNT(*) FROM inventory_logs\n")
        sql.write("UNION ALL SELECT 'audit_logs', COUNT(*) FROM audit_logs;\n")

    STATS_PATH.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    print("旧版 generate_historical_sql.py 已停用：当前 schema 已拆分 customers/suppliers。")
    print("请使用 scripts/generate_partner_data.py，或直接导入 sql/seed_2022_09_12_2026_10_01.sql。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
