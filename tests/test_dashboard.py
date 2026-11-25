"""老板看板测试：今日/本月销售额与 Top 5。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo


async def _sell(client, headers, customer_id: int, part_id: int, quantity: int) -> None:
    response = await client.post(
        "/api/v1/sales/outbound",
        json={"customer_id": customer_id, "items": [{"part_id": part_id, "quantity": quantity}]},
        headers=headers,
    )
    assert response.status_code == 201, response.text


async def test_dashboard_totals_and_top_parts(client, seed_data, boss_headers):
    # 柴油滤清器 3 件 * 25.00 = 75.00
    await _sell(client, boss_headers, seed_data["customer_id"], seed_data["part_id"], 3)
    # 植保机喷头 2 件 * 68.00 = 136.00
    await _sell(client, boss_headers, seed_data["customer_id"], seed_data["low_part_id"], 2)

    response = await client.get("/api/v1/dashboard", headers=boss_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert Decimal(body["today_sales_amount"]) == Decimal("211.00")
    assert Decimal(body["month_sales_amount"]) == Decimal("211.00")
    assert body["today_order_count"] == 2
    assert body["month_order_count"] == 2

    assert len(body["top_parts"]) == 2
    assert body["top_parts"][0]["part_name"] == "柴油滤清器"
    assert body["top_parts"][0]["quantity"] == 3
    assert body["top_parts"][1]["part_name"] == "植保机喷头"
    assert body["top_parts"][1]["quantity"] == 2
    assert body["generated_at"]


async def test_dashboard_is_boss_only(client, seed_data, employee_headers):
    response = await client.get("/api/v1/dashboard", headers=employee_headers)

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


async def test_dashboard_returns_zero_when_no_sales(client, seed_data, boss_headers):
    response = await client.get("/api/v1/dashboard", headers=boss_headers)

    assert response.status_code == 200
    body = response.json()
    assert Decimal(body["today_sales_amount"]) == Decimal("0.00")
    assert Decimal(body["month_sales_amount"]) == Decimal("0.00")
    assert body["top_parts"] == []


async def test_dashboard_report_date_range_and_metrics(client, seed_data, boss_headers):
    """指定日期区间：销售、成本、毛利、排行、分类和趋势口径一致。"""
    await _sell(client, boss_headers, seed_data["customer_id"], seed_data["part_id"], 3)
    await _sell(client, boss_headers, seed_data["customer_id"], seed_data["low_part_id"], 2)

    today = datetime.now(UTC).astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
    response = await client.get(
        "/api/v1/dashboard/report",
        params={"start_date": today, "end_date": today},
        headers=boss_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["start_date"] == today
    assert body["end_date"] == today
    assert body["data_start_date"] == today
    assert body["data_end_date"] == today
    assert Decimal(body["sales_amount"]) == Decimal("211.00")
    assert body["sales_order_count"] == 2
    assert body["items_sold"] == 5
    assert Decimal(body["avg_order_amount"]) == Decimal("105.50")
    assert Decimal(body["purchase_amount"]) == Decimal("0.00")
    assert Decimal(body["gross_profit"]) == Decimal("103.50")
    assert Decimal(body["gross_margin"]) == Decimal("49.05")
    assert body["trend_granularity"] == "day"
    assert body["trend"] == [{"period": today, "sales_amount": "211.00", "order_count": 2}]

    assert body["top_parts"][0]["part_name"] == "植保机喷头"
    assert body["top_parts"][0]["quantity"] == 2
    assert Decimal(body["top_parts"][0]["amount"]) == Decimal("136.00")
    assert body["top_customers"][0]["customer_name"] == "王建军"
    assert Decimal(body["top_customers"][0]["amount"]) == Decimal("211.00")
    assert sum(Decimal(item["amount"]) for item in body["category_breakdown"]) == Decimal("211.00")


async def test_dashboard_report_empty_range_and_invalid_range(client, seed_data, boss_headers):
    await _sell(client, boss_headers, seed_data["customer_id"], seed_data["part_id"], 1)
    today = datetime.now(UTC).astimezone(ZoneInfo("Asia/Shanghai")).date()
    yesterday = (today - timedelta(days=1)).isoformat()

    empty = await client.get(
        "/api/v1/dashboard/report",
        params={"start_date": yesterday, "end_date": yesterday},
        headers=boss_headers,
    )
    assert empty.status_code == 200, empty.text
    body = empty.json()
    assert Decimal(body["sales_amount"]) == Decimal("0.00")
    assert body["sales_order_count"] == 0
    assert body["top_parts"] == []
    assert body["trend"] == []
    assert body["data_start_date"] == today.isoformat()

    invalid = await client.get(
        "/api/v1/dashboard/report",
        params={"start_date": today.isoformat(), "end_date": yesterday},
        headers=boss_headers,
    )
    assert invalid.status_code == 400
    assert invalid.json()["code"] == "INVALID_DATE_RANGE"


async def test_dashboard_report_is_boss_only(client, seed_data, employee_headers):
    response = await client.get("/api/v1/dashboard/report", headers=employee_headers)

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"
