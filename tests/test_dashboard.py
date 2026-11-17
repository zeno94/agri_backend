"""老板看板测试：今日/本月销售额与 Top 5。"""

from __future__ import annotations

from decimal import Decimal


async def _sell(client, headers, customer_id: int, part_id: int, quantity: int) -> None:
    response = await client.post(
        "/api/v1/sales/outbound",
        json={"partner_id": customer_id, "items": [{"part_id": part_id, "quantity": quantity}]},
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
