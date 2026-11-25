"""现有 Vue 前端的接口契约测试。

对照 agri_frontend/src/api 与页面实际请求，确保：
- /suppliers/options、/customers/options 下拉入口存在；
- 配件列表支持 page_size=1000；
- 新增配件支持 price（映射 sale_price）；
- 采购单支持 supplier_id + unit_price；
- 销售单支持 customer_id + 单条 part_id/quantity。
"""

from __future__ import annotations

from decimal import Decimal


async def test_suppliers_and_customers_option_lists(client, seed_data, boss_headers):
    suppliers = await client.get("/api/v1/suppliers/options", headers=boss_headers)
    assert suppliers.status_code == 200, suppliers.text
    supplier_body = suppliers.json()
    assert supplier_body["total"] == 1
    assert supplier_body["items"][0]["name"] == "杞县丰农农机配件有限公司"

    customers = await client.get("/api/v1/customers/options", headers=boss_headers)
    assert customers.status_code == 200, customers.text
    customer_body = customers.json()
    assert customer_body["total"] == 1
    assert customer_body["items"][0]["name"] == "王建军"


async def test_parts_list_accepts_frontend_page_size(client, seed_data, boss_headers):
    response = await client.get(
        "/api/v1/parts",
        params={"page": 1, "page_size": 1000, "name": "滤清"},
        headers=boss_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["name"] == "柴油滤清器"


async def test_create_part_accepts_frontend_price_payload(client, seed_data, boss_headers):
    response = await client.post(
        "/api/v1/parts",
        json={
            "name": "LED 前照灯",
            "model": "LED-12V",
            "brand": "福田",
            "category": "灯具",
            "stock": 5,
            "safe_stock": 2,
            "price": 88.5,
        },
        headers=boss_headers,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert Decimal(body["sale_price"]) == Decimal("88.50")
    assert Decimal(body["purchase_price"]) == Decimal("0.00")


async def test_purchase_inbound_accepts_supplier_id_and_unit_price(client, seed_data, boss_headers):
    response = await client.post(
        "/api/v1/purchases/inbound",
        json={
            "supplier_id": seed_data["supplier_id"],
            "items": [{"part_id": seed_data["part_id"], "quantity": 2, "unit_price": "13.00"}],
        },
        headers=boss_headers,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["supplier_id"] == seed_data["supplier_id"]
    assert Decimal(body["total_amount"]) == Decimal("26.00")
    assert Decimal(body["items"][0]["price"]) == Decimal("13.00")

    part = await client.get(f"/api/v1/parts/{seed_data['part_id']}", headers=boss_headers)
    assert part.json()["stock"] == 12


async def test_sale_outbound_accepts_single_item_frontend_payload(client, seed_data, boss_headers):
    response = await client.post(
        "/api/v1/sales/outbound",
        json={
            "customer_id": seed_data["customer_id"],
            "part_id": seed_data["part_id"],
            "quantity": 3,
        },
        headers=boss_headers,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["customer_id"] == seed_data["customer_id"]
    assert Decimal(body["total_amount"]) == Decimal("75.00")
    assert Decimal(body["items"][0]["price"]) == Decimal("25.00")
    assert body["items"][0]["quantity"] == 3

    part = await client.get(f"/api/v1/parts/{seed_data['part_id']}", headers=boss_headers)
    assert part.json()["stock"] == 7
