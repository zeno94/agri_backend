"""给演示库追加「灌溉设备」品类，并生成与现有数据同口径的历史流水。

为什么单独写一个脚本而不是改 generate_historical_sql.py：
后者已标注【旧版已停用】——它仍写 partners/partner_id 老 schema，跑起来会破坏当前库。
所以这里做成「增量追加」：不动现有 126 个 SKU 和 8,820 张单，只新增灌溉品类及其流水。

数据口径（与现有数据保持一致）：
- 销售明细单价为整数元，订单总额 = 明细金额之和；
- 采购价保留两位小数，按成本上下浮动 ±4%；
- 销售价在零售价基础上打 92%~100% 折扣，且不低于成本 × 1.08；
- 时间：本地 Asia/Shanghai 07:35~20:13 生成，落库为 naive UTC；
- 库存逐笔仿真，任何时点不为负；每次变动写 inventory_logs 的 before/after 快照。

价格来源见 sql/DATA_SOURCES.md，取「电商/批发公开报价 × 县域零售加价」，
品牌与型号均为真实在售型号（QDX/QY/QJ 系列、手摇轱辘井架等）。

用法：
    .venv/bin/python scripts/seed_irrigation_data.py --dry-run   # 只看计划
    .venv/bin/python scripts/seed_irrigation_data.py             # 实际写入
"""

from __future__ import annotations

import argparse
import random
import re
import sys
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pymysql

ROOT = Path(__file__).resolve().parent.parent
TZ = ZoneInfo("Asia/Shanghai")
RNG = random.Random(20261125)

START_DAY = date(2022, 9, 12)
END_DAY = date(2026, 10, 1)

# 灌溉设备的淡旺季：春灌(3-5月)与夏灌(6-8月)是高峰，冬季基本不动
MONTH_FACTOR = {
    1: 0.15, 2: 0.25, 3: 0.80, 4: 1.45, 5: 1.30,
    6: 1.50, 7: 1.25, 8: 0.85, 9: 0.55, 10: 0.45,
    11: 0.25, 12: 0.15,
}

# 水泵类供应商 / 配件类供应商
PUMP_SUPPLIER = 104      # 杞县惠农水泵销售中心
PARTS_SUPPLIER = 103     # 杞县中原农机配件销售中心

# name, model, brand, category, cost, retail, safe_stock, 需求权重, 单次销量区间
SPECS: list[tuple[str, str, str, str, str, str, int, float, tuple[int, int]]] = [
    # ---- 潜水泵（QDX 单相清水泵）----
    ("潜水泵 QDX3-18-0.55", "QDX3-18-0.55", "新界", "潜水泵", "235.00", "310.00", 3, 3.2, (1, 2)),
    ("潜水泵 QDX10-10-0.75", "QDX10-10-0.75", "新界", "潜水泵", "295.00", "390.00", 3, 2.8, (1, 2)),
    ("潜水泵 QDX40-6-1.1", "QDX40-6-1.1", "臣源", "潜水泵", "420.00", "550.00", 3, 2.4, (1, 2)),
    ("潜水泵 QDX15-14-1.1", "QDX15-14-1.1", "大元", "潜水泵", "465.00", "610.00", 2, 2.0, (1, 2)),
    # ---- 潜水泵（QY 油浸式三相泵）----
    ("油浸式潜水泵 QY25-26-3", "QY25-26-3", "神农", "潜水泵", "1050.00", "1380.00", 2, 1.6, (1, 1)),
    ("油浸式潜水泵 QY65-7-2.2", "QY65-7-2.2", "凌民", "潜水泵", "760.00", "990.00", 2, 1.8, (1, 1)),
    ("油浸式潜水泵 QY25-32-4A", "QY25-32-4A", "欧隆", "潜水泵", "2450.00", "3200.00", 1, 0.8, (1, 1)),
    # ---- 深井潜水泵（QJ 多级）----
    ("深井潜水泵 QJ10-100/20-5.5", "QJ10-100/20-5.5", "利欧", "潜水泵", "2250.00", "2950.00", 1, 0.9, (1, 1)),
    ("深井潜水泵 QJ20-80/10-7.5", "QJ20-80/10-7.5", "新界", "潜水泵", "3150.00", "4100.00", 1, 0.6, (1, 1)),
    ("深井潜水泵 QJ32-52/6-7.5", "QJ32-52/6-7.5", "南方", "潜水泵", "3680.00", "4780.00", 1, 0.5, (1, 1)),
    # ---- 井架 / 吊泵架 ----
    ("手摇轱辘井架 1吨", "GC-1T", "历天景", "井架/吊具", "285.00", "380.00", 2, 1.6, (1, 1)),
    ("吊泵三脚架配1吨手拉葫芦", "SJ-1T", "历天景", "井架/吊具", "420.00", "560.00", 2, 1.4, (1, 1)),
    ("吊泵三脚架配2吨手拉葫芦", "SJ-2T", "历天景", "井架/吊具", "640.00", "850.00", 1, 0.7, (1, 1)),
    ("井架钢丝绳 6mm 25米", "GS-6-25", "永固", "井架/吊具", "48.00", "70.00", 8, 2.2, (1, 3)),
    ("机井口防坠盖板 80cm", "FZ-80", "永固", "井架/吊具", "42.00", "62.00", 6, 1.2, (1, 2)),
    # ---- 灌溉配件 ----
    ("潜水泵专用电缆 3×2.5", "DL-325", "豫缆", "灌溉配件", "11.00", "16.00", 60, 3.0, (10, 50)),
    ("PVC出水管 1.5寸", "PVC-15", "联塑", "灌溉配件", "7.50", "11.00", 80, 2.6, (10, 40)),
    ("快速接头 1.5寸", "KT-15", "丰泉", "灌溉配件", "14.00", "21.00", 20, 1.8, (1, 4)),
    ("潜水泵启动电容 450V", "DR-450", "正泰", "灌溉配件", "16.00", "25.00", 20, 1.4, (1, 3)),
    ("潜水泵综合保护器 7.5kW", "BH-7.5", "正泰", "灌溉配件", "88.00", "130.00", 6, 1.0, (1, 2)),
]


def money(value: Decimal | str | float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def load_dsn() -> dict:
    env = (ROOT / ".env").read_text()
    url = [line for line in env.splitlines() if line.startswith("DATABASE_URL")][0]
    match = re.search(r"//([^:]+):([^@]+)@([^:]+):(\d+)/([^?]+)", url)
    user, pwd, host, port, db = match.groups()
    return dict(host=host, port=int(port), user=user, password=pwd, database=db, charset="utf8mb4")


def local_to_utc_naive(day: date, hour: int, minute: int) -> datetime:
    local = datetime.combine(day, time(hour, minute), tzinfo=TZ)
    return local.astimezone(UTC).replace(tzinfo=None)


def random_trade_time(day: date) -> tuple[int, int]:
    hour = RNG.choices([8, 9, 10, 11, 13, 14, 15, 16, 17, 18], weights=[6, 9, 11, 9, 8, 10, 10, 9, 7, 5])[0]
    return hour, RNG.randint(0, 59)


class Simulator:
    def __init__(self, conn, dry_run: bool) -> None:
        self.conn = conn
        self.dry_run = dry_run
        self.cursor = conn.cursor()

        # 已有数据的序号基线
        self.sale_seq: dict[str, int] = {}
        self.purchase_seq: dict[str, int] = {}
        self._load_order_sequences()

        self.cursor.execute("select id from customers")
        self.customers = [row[0] for row in self.cursor.fetchall()]
        self.cursor.execute("select id, username from users")
        self.users = self.cursor.fetchall()

        self.sale_orders: list[tuple] = []
        self.sale_items: list[tuple] = []
        self.purchase_orders: list[tuple] = []
        self.purchase_items: list[tuple] = []
        self.inventory_logs: list[tuple] = []

    # ---------- 读取现有单号，保证不撞号 ----------
    def _load_order_sequences(self) -> None:
        for table, bucket in (("sale_orders", self.sale_seq), ("purchase_orders", self.purchase_seq)):
            self.cursor.execute(f"select order_no from {table}")
            for (order_no,) in self.cursor.fetchall():
                match = re.match(r"^(SO|PO)(\d{8})(\d{4})$", order_no)
                if not match:
                    continue
                day, seq = match.group(2), int(match.group(3))
                bucket[day] = max(bucket.get(day, 0), seq)

    def _next_no(self, prefix: str, day: date) -> str:
        key = day.strftime("%Y%m%d")
        bucket = self.sale_seq if prefix == "SO" else self.purchase_seq
        nxt = bucket.get(key, 0) + 1
        bucket[key] = nxt
        return f"{prefix}{key}{nxt:04d}"

    def _operator(self) -> int:
        # 员工开单为主，老板偶尔自己开
        return RNG.choices([self.users[1][0], self.users[2][0], self.users[0][0]], weights=[5, 4, 1])[0]

    def create_products(self) -> list[dict]:
        products = []
        for name, model, brand, category, cost, retail, safe_stock, weight, qty_range in SPECS:
            created = local_to_utc_naive(START_DAY, 8, 0)
            products.append(
                dict(
                    name=name, model=model, brand=brand, category=category,
                    cost=money(cost), retail=money(retail),
                    safe_stock=safe_stock, weight=weight, qty_range=qty_range,
                    stock=0, id=None, created_at=created,
                )
            )
        return products

    # ---------- 采购入库 ----------
    def buy(self, day: date, items: list[tuple[dict, int]]) -> None:
        if not items:
            return
        total = Decimal("0.00")
        order_no = self._next_no("PO", day)
        hour, minute = random_trade_time(day)
        created = local_to_utc_naive(day, hour, minute)
        operator = self._operator()
        supplier = PUMP_SUPPLIER if all(p["category"] == "潜水泵" for p, _ in items) else PARTS_SUPPLIER

        lines = []
        for product, qty in items:
            price = money(product["cost"] * Decimal(str(RNG.uniform(0.96, 1.04))))
            total += price * qty
            lines.append((order_no, product, qty, price, created, operator))
            before = product["stock"]
            product["stock"] = before + qty
            self.inventory_logs.append(
                (product["id"], "in", qty, operator, f"采购入库 {order_no}", created,
                 before, product["stock"])
            )
        self.purchase_orders.append((order_no, money(total), "completed", operator, created, supplier, None))
        self.purchase_items.extend(lines)

    # ---------- 销售出库 ----------
    def sell(self, day: date, picks: list[tuple[dict, int]]) -> None:
        if not picks:
            return
        order_no = self._next_no("SO", day)
        hour, minute = random_trade_time(day)
        created = local_to_utc_naive(day, hour, minute)
        operator = self._operator()
        customer = RNG.choice(self.customers)
        total = Decimal("0.00")
        lines = []
        for product, qty in picks:
            discount = RNG.uniform(0.94, 1.0) if product["retail"] >= 800 else RNG.uniform(0.92, 1.0)
            raw = product["retail"] * Decimal(str(discount))
            floor = product["cost"] * Decimal("1.08")
            price = Decimal(int(max(raw, floor).to_integral_value(rounding=ROUND_HALF_UP)))
            total += price * qty
            lines.append((order_no, product, qty, price, created, operator))
            before = product["stock"]
            product["stock"] = before - qty
            self.inventory_logs.append(
                (product["id"], "out", -qty, operator, f"销售出库 {order_no}", created,
                 before, product["stock"])
            )
        remark = RNG.choice([None, None, None, "春灌备货", "抗旱浇地"])
        self.sale_orders.append((order_no, money(total), "completed", operator, created, customer, remark))
        self.sale_items.extend(lines)

    # ---------- 主循环 ----------
    def run(self) -> dict:
        products = self.create_products()
        self.products = products

        if not self.dry_run:
            for product in products:
                self.cursor.execute(
                    """insert into parts (name, model, category, brand, stock, safe_stock,
                                          purchase_price, sale_price, created_at, updated_at)
                       values (%s,%s,%s,%s,0,%s,%s,%s,%s,%s)""",
                    (product["name"], product["model"], product["category"], product["brand"],
                     product["safe_stock"], product["cost"], product["retail"],
                     product["created_at"], product["created_at"]),
                )
                product["id"] = self.cursor.lastrowid
        else:
            self.cursor.execute("select coalesce(max(id),0) from parts")
            base = self.cursor.fetchone()[0]
            for idx, product in enumerate(products, start=1):
                product["id"] = base + idx

        # 期初备货
        opening = [(p, max(p["qty_range"][1], 3) * (6 if p["category"] == "灌溉配件" else 2)) for p in products]
        self.buy(START_DAY, opening)

        day = START_DAY
        while day <= END_DAY:
            factor = MONTH_FACTOR[day.month]
            # 补货：低于安全库存就补
            restock = []
            for product in products:
                if product["stock"] <= product["safe_stock"]:
                    if product["category"] == "灌溉配件":
                        qty = RNG.randint(60, 160)
                    elif product["category"] == "井架/吊具":
                        qty = RNG.randint(3, 6)
                    else:
                        qty = RNG.randint(2, 5)
                    restock.append((product, qty))
            if restock:
                self.buy(day, restock)

            # 销售：按季节波动
            p_order = 0.34 * factor
            n_orders = 0
            if RNG.random() < p_order:
                n_orders = 1
                if RNG.random() < 0.28 * factor:
                    n_orders = 2
            for _ in range(n_orders):
                pool = [p for p in products if p["stock"] > 0]
                if not pool:
                    break
                n_lines = 1 if RNG.random() < 0.72 else 2
                picks: list[tuple[dict, int]] = []
                chosen: set[int] = set()
                for _ in range(n_lines):
                    candidates = [p for p in pool if id(p) not in chosen]
                    if not candidates:
                        break
                    product = RNG.choices(candidates, weights=[p["weight"] for p in candidates])[0]
                    lo, hi = product["qty_range"]
                    qty = min(RNG.randint(lo, hi), product["stock"])
                    if qty <= 0:
                        continue
                    picks.append((product, qty))
                    chosen.add(id(product))
                self.sell(day, picks)

            day += timedelta(days=1)

        return {"products": products}

    # ---------- 落库 ----------
    def flush(self) -> None:
        if self.dry_run:
            return
        cur = self.cursor
        cur.executemany(
            "insert into purchase_orders (order_no, total_amount, status, operator_id, created_at, supplier_id, remark)"
            " values (%s,%s,%s,%s,%s,%s,%s)",
            [(n, t, s, o, c, sup, r) for n, t, s, o, c, sup, r in self.purchase_orders],
        )
        id_map = {}
        cur.execute("select order_no, id from purchase_orders")
        for order_no, oid in cur.fetchall():
            id_map[order_no] = oid
        cur.executemany(
            "insert into purchase_items (order_id, part_id, quantity, price) values (%s,%s,%s,%s)",
            [(id_map[n], p["id"], q, price) for n, p, q, price, _c, _o in self.purchase_items],
        )

        cur.executemany(
            "insert into sale_orders (order_no, total_amount, status, operator_id, created_at, customer_id, remark)"
            " values (%s,%s,%s,%s,%s,%s,%s)",
            [(n, t, s, o, c, cust, r) for n, t, s, o, c, cust, r in self.sale_orders],
        )
        id_map = {}
        cur.execute("select order_no, id from sale_orders")
        for order_no, oid in cur.fetchall():
            id_map[order_no] = oid
        cur.executemany(
            "insert into sale_items (order_id, part_id, quantity, price) values (%s,%s,%s,%s)",
            [(id_map[n], p["id"], q, price) for n, p, q, price, _c, _o in self.sale_items],
        )

        cur.executemany(
            "insert into inventory_logs (part_id, change_type, change_qty, operator_id, remark, created_at,"
            " before_stock, after_stock) values (%s,%s,%s,%s,%s,%s,%s,%s)",
            self.inventory_logs,
        )
        # 把仿真结束时的库存写回 parts
        cur.executemany(
            "update parts set stock=%s, updated_at=%s where id=%s",
            [(p["stock"], local_to_utc_naive(END_DAY, 20, 0), p["id"]) for p in self.products],
        )
        self.conn.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description="追加灌溉设备品类与历史流水")
    parser.add_argument("--dry-run", action="store_true", help="只模拟不写库")
    args = parser.parse_args()

    dsn = load_dsn()
    conn = pymysql.connect(**dsn)
    cur = conn.cursor()
    # timestamp 列会按会话时区换算：这里固定 UTC，避免本地 +08:00 会话把值再偏一次
    cur.execute("SET time_zone = '+00:00'")
    cur.execute("select count(*) from parts where category in ('潜水泵','井架/吊具','灌溉配件')")
    if cur.fetchone()[0]:
        print("库里已经有灌溉品类，先回滚/重导快照再跑，避免重复追加", file=sys.stderr)
        return 1

    sim = Simulator(conn, args.dry_run)
    result = sim.run()
    products = result["products"]
    sim.flush()

    sales_total = sum(Decimal(str(t)) for _n, t, *_ in sim.sale_orders)
    purchase_total = sum(Decimal(str(t)) for _n, t, *_ in sim.purchase_orders)
    print(f"新增 SKU: {len(products)}")
    for category in ("潜水泵", "井架/吊具", "灌溉配件"):
        items = [p for p in products if p["category"] == category]
        print(f"  {category}: {len(items)} 个")
    print(f"新增采购单: {len(sim.purchase_orders)} 张 / {len(sim.purchase_items)} 行 / ¥{purchase_total:,}")
    print(f"新增销售单: {len(sim.sale_orders)} 张 / {len(sim.sale_items)} 行 / ¥{sales_total:,}")
    print(f"新增库存流水: {len(sim.inventory_logs)} 条")
    print("期末库存:")
    for p in products:
        print(f"  {p['name']}: {p['stock']}")
    if args.dry_run:
        print("\n[dry-run] 未写入数据库")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
