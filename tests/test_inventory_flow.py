"""采购入库、销售出库（防超卖）与库存流水测试。"""

from __future__ import annotations

from decimal import Decimal


async def _get_part(client, part_id: int, headers) -> dict:
    response = await client.get(f"/api/v1/parts/{part_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def _create_simple_part(client, headers, name: str, stock: int, safe_stock: int = 0) -> int:
    response = await client.post(
        "/api/v1/parts",
        json={
            "name": name,
            "model": f"{name}-M",
            "category": "测试分类",
            "brand": "测试品牌",
            "stock": stock,
            "safe_stock": safe_stock,
            "purchase_price": "10.00",
            "sale_price": "20.00",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_purchase_inbound_increases_stock_and_writes_log(client, seed_data, boss_headers):
    response = await client.post(
        "/api/v1/purchases/inbound",
        json={
            "partner_id": seed_data["supplier_id"],
            "items": [{"part_id": seed_data["part_id"], "quantity": 5, "price": "13.00"}],
            "remark": "月度补货",
        },
        headers=boss_headers,
    )

    assert response.status_code == 201, response.text
    order = response.json()
    assert order["status"] == "completed"
    assert order["partner_name"] == "潍坊配件厂"
    assert order["operator_name"] == "boss"
    assert order["items"][0]["part_name"] == "柴油滤清器"
    assert Decimal(order["items"][0]["amount"]) == Decimal("65.00")
    assert Decimal(order["total_amount"]) == Decimal("65.00")
    assert order["order_no"].startswith("PO")

    part = await _get_part(client, seed_data["part_id"], boss_headers)
    assert part["stock"] == 15

    logs = await client.get(
        "/api/v1/inventory/logs",
        params={"part_id": seed_data["part_id"], "change_type": "in"},
        headers=boss_headers,
    )
    assert logs.status_code == 200
    assert logs.json()["total"] == 1
    log = logs.json()["items"][0]
    assert log["change_qty"] == 5
    assert log["before_stock"] == 10
    assert log["after_stock"] == 15
    assert log["operator_name"] == "boss"

    order_list = await client.get("/api/v1/purchases", headers=boss_headers)
    assert order_list.json()["total"] == 1


async def test_purchase_requires_supplier_partner(client, seed_data, boss_headers):
    response = await client.post(
        "/api/v1/purchases/inbound",
        json={
            "partner_id": seed_data["customer_id"],
            "items": [{"part_id": seed_data["part_id"], "quantity": 1}],
        },
        headers=boss_headers,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "PARTNER_TYPE_INVALID"


async def test_purchase_with_missing_part_rolls_back(client, seed_data, boss_headers):
    response = await client.post(
        "/api/v1/purchases/inbound",
        json={
            "partner_id": seed_data["supplier_id"],
            "items": [
                {"part_id": seed_data["part_id"], "quantity": 2},
                {"part_id": 999999, "quantity": 1},
            ],
        },
        headers=boss_headers,
    )

    assert response.status_code == 404
    assert response.json()["code"] == "PART_NOT_FOUND"

    part = await _get_part(client, seed_data["part_id"], boss_headers)
    assert part["stock"] == 10
    orders = await client.get("/api/v1/purchases", headers=boss_headers)
    assert orders.json()["total"] == 0


async def test_sale_outbound_deducts_stock_and_writes_log(client, seed_data, boss_headers):
    response = await client.post(
        "/api/v1/sales/outbound",
        json={
            "partner_id": seed_data["customer_id"],
            "items": [{"part_id": seed_data["part_id"], "quantity": 4}],
        },
        headers=boss_headers,
    )

    assert response.status_code == 201, response.text
    order = response.json()
    assert order["status"] == "completed"
    assert order["partner_name"] == "绿野合作社"
    assert order["items"][0]["price"] == "25.00"  # 未传单价时取配件销售价
    assert Decimal(order["total_amount"]) == Decimal("100.00")

    part = await _get_part(client, seed_data["part_id"], boss_headers)
    assert part["stock"] == 6

    logs = await client.get(
        "/api/v1/inventory/logs",
        params={"part_id": seed_data["part_id"], "change_type": "out"},
        headers=boss_headers,
    )
    log = logs.json()["items"][0]
    assert log["change_qty"] == -4
    assert log["before_stock"] == 10
    assert log["after_stock"] == 6


async def test_sale_outbound_rejects_oversell_and_rolls_back(client, seed_data, boss_headers):
    response = await client.post(
        "/api/v1/sales/outbound",
        json={
            "partner_id": seed_data["customer_id"],
            "items": [{"part_id": seed_data["part_id"], "quantity": 11}],
        },
        headers=boss_headers,
    )

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "INSUFFICIENT_STOCK"
    shortage = body["detail"]["items"][0]
    assert shortage["requested"] == 11
    assert shortage["available"] == 10

    # 库存、单据、流水都不应发生变化
    part = await _get_part(client, seed_data["part_id"], boss_headers)
    assert part["stock"] == 10

    sales = await client.get("/api/v1/sales", headers=boss_headers)
    assert sales.json()["total"] == 0

    out_logs = await client.get(
        "/api/v1/inventory/logs",
        params={"change_type": "out"},
        headers=boss_headers,
    )
    assert out_logs.json()["total"] == 0


async def test_multi_item_sale_is_atomic_when_one_item_is_short(client, seed_data, boss_headers):
    """两条明细中第二条库存不足时，第一条也不能被扣减（先校验后扣减）。"""
    other_part_id = await _create_simple_part(client, boss_headers, "备用喷油嘴", stock=1)

    response = await client.post(
        "/api/v1/sales/outbound",
        json={
            "partner_id": seed_data["customer_id"],
            "items": [
                {"part_id": seed_data["part_id"], "quantity": 2},
                {"part_id": other_part_id, "quantity": 5},
            ],
        },
        headers=boss_headers,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "INSUFFICIENT_STOCK"

    first = await _get_part(client, seed_data["part_id"], boss_headers)
    second = await _get_part(client, other_part_id, boss_headers)
    assert first["stock"] == 10
    assert second["stock"] == 1

    sales = await client.get("/api/v1/sales", headers=boss_headers)
    assert sales.json()["total"] == 0

    out_logs = await client.get(
        "/api/v1/inventory/logs",
        params={"change_type": "out"},
        headers=boss_headers,
    )
    assert out_logs.json()["total"] == 0


async def test_sale_rejects_duplicate_parts(client, seed_data, boss_headers):
    response = await client.post(
        "/api/v1/sales/outbound",
        json={
            "partner_id": seed_data["customer_id"],
            "items": [
                {"part_id": seed_data["part_id"], "quantity": 1},
                {"part_id": seed_data["part_id"], "quantity": 2},
            ],
        },
        headers=boss_headers,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


async def test_sale_requires_customer_partner(client, seed_data, boss_headers):
    response = await client.post(
        "/api/v1/sales/outbound",
        json={
            "partner_id": seed_data["supplier_id"],
            "items": [{"part_id": seed_data["part_id"], "quantity": 1}],
        },
        headers=boss_headers,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "PARTNER_TYPE_INVALID"


async def test_sale_with_fixed_price_and_multiple_items(client, seed_data, boss_headers):
    response = await client.post(
        "/api/v1/sales/outbound",
        json={
            "partner_id": seed_data["customer_id"],
            "items": [
                {"part_id": seed_data["part_id"], "quantity": 2, "price": "24.50"},
                {"part_id": seed_data["low_part_id"], "quantity": 2, "price": "66.00"},
            ],
            "remark": "现场结算",
        },
        headers=boss_headers,
    )

    assert response.status_code == 201, response.text
    order = response.json()
    assert Decimal(order["total_amount"]) == Decimal("181.00")
    assert len(order["items"]) == 2
    assert order["remark"] == "现场结算"
