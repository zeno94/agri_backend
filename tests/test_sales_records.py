"""销售记录分页与筛选测试。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo


async def _sell(client, headers, customer_id: int, part_id: int, quantity: int) -> dict:
    response = await client.post(
        "/api/v1/sales/outbound",
        json={"customer_id": customer_id, "items": [{"part_id": part_id, "quantity": quantity}]},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_sales_records_filters_and_total_amount(client, seed_data, boss_headers, employee_headers):
    first = await _sell(client, boss_headers, seed_data["customer_id"], seed_data["part_id"], 2)
    second = await _sell(client, boss_headers, seed_data["customer_id"], seed_data["low_part_id"], 1)
    today = datetime.now(UTC).astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()

    all_sales = await client.get("/api/v1/sales", headers=boss_headers)
    assert all_sales.status_code == 200, all_sales.text
    body = all_sales.json()
    assert body["total"] == 2
    assert Decimal(body["total_amount"]) == Decimal("118.00")
    assert len(body["items"]) == 2

    by_customer = await client.get(
        "/api/v1/sales",
        params={"customer_id": seed_data["customer_id"], "start_date": today, "end_date": today},
        headers=boss_headers,
    )
    assert by_customer.status_code == 200, by_customer.text
    assert by_customer.json()["total"] == 2
    assert Decimal(by_customer.json()["total_amount"]) == Decimal("118.00")

    by_keyword = await client.get(
        "/api/v1/sales",
        params={"keyword": first["order_no"][-6:]},
        headers=boss_headers,
    )
    assert by_keyword.status_code == 200, by_keyword.text
    keyword_body = by_keyword.json()
    assert keyword_body["total"] == 1
    assert keyword_body["items"][0]["order_no"] == first["order_no"]
    assert Decimal(keyword_body["total_amount"]) == Decimal("50.00")

    paged = await client.get("/api/v1/sales", params={"page": 2, "size": 1}, headers=boss_headers)
    assert paged.status_code == 200, paged.text
    assert paged.json()["total"] == 2
    assert paged.json()["pages"] == 2
    assert len(paged.json()["items"]) == 1

    # 区间外的单据不参与合计
    yesterday = (datetime.now(UTC).astimezone(ZoneInfo("Asia/Shanghai")).date() - timedelta(days=1)).isoformat()
    empty = await client.get(
        "/api/v1/sales",
        params={"start_date": yesterday, "end_date": yesterday},
        headers=boss_headers,
    )
    assert empty.status_code == 200, empty.text
    assert empty.json()["total"] == 0
    assert Decimal(empty.json()["total_amount"]) == Decimal("0.00")

    invalid = await client.get(
        "/api/v1/sales",
        params={"start_date": today, "end_date": yesterday},
        headers=boss_headers,
    )
    assert invalid.status_code == 400
    assert invalid.json()["code"] == "INVALID_DATE_RANGE"

    # 员工可查看全部销售记录，但价格权限仍由出库接口控制
    employee = await client.get("/api/v1/sales", headers=employee_headers)
    assert employee.status_code == 200, employee.text
    assert employee.json()["total"] == 2
    assert second["order_no"] in {item["order_no"] for item in employee.json()["items"]}
