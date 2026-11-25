"""幂等键测试：同一个 Idempotency-Key 重复提交只执行一次。"""

from __future__ import annotations

from decimal import Decimal


def _sale_payload(seed_data) -> dict:
    return {
        "customer_id": seed_data["customer_id"],
        "items": [{"part_id": seed_data["part_id"], "quantity": 2}],
        "remark": "幂等测试",
    }


async def _stock(client, part_id: int, headers) -> int:
    response = await client.get(f"/api/v1/parts/{part_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["stock"]


async def test_same_key_executes_once_and_replays(client, seed_data, boss_headers, fake_redis):
    headers = {**boss_headers, "Idempotency-Key": "test-key-replay-0001"}

    first = await client.post("/api/v1/sales/outbound", json=_sale_payload(seed_data), headers=headers)
    assert first.status_code == 201, first.text

    second = await client.post("/api/v1/sales/outbound", json=_sale_payload(seed_data), headers=headers)
    assert second.status_code == 201, second.text

    # 回放的是同一张单，且带上了标记头
    assert second.headers.get("idempotent-replay") == "true"
    assert second.json()["order_no"] == first.json()["order_no"]
    assert second.json()["id"] == first.json()["id"]

    # 库存只扣了一次（10 - 2），也没有第二张单
    assert await _stock(client, seed_data["part_id"], boss_headers) == 8
    orders = await client.get("/api/v1/sales", headers=boss_headers)
    assert orders.json()["total"] == 1


async def test_different_keys_create_separate_orders(client, seed_data, boss_headers):
    payload = _sale_payload(seed_data)
    first = await client.post(
        "/api/v1/sales/outbound",
        json=payload,
        headers={**boss_headers, "Idempotency-Key": "test-key-a-0001"},
    )
    second = await client.post(
        "/api/v1/sales/outbound",
        json=payload,
        headers={**boss_headers, "Idempotency-Key": "test-key-b-0002"},
    )
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["order_no"] != second.json()["order_no"]
    assert await _stock(client, seed_data["part_id"], boss_headers) == 6


async def test_without_key_behaves_as_before(client, seed_data, boss_headers):
    """不传幂等键时保持旧行为：两次请求两张单（向后兼容）。"""
    payload = _sale_payload(seed_data)
    first = await client.post("/api/v1/sales/outbound", json=payload, headers=boss_headers)
    second = await client.post("/api/v1/sales/outbound", json=payload, headers=boss_headers)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["order_no"] != second.json()["order_no"]


async def test_invalid_key_is_rejected(client, seed_data, boss_headers):
    # 3 位太短（要求 8~64 位）。注意 HTTP 头只能放 ASCII，所以这里用短字符串而不是中文。
    response = await client.post(
        "/api/v1/sales/outbound",
        json=_sale_payload(seed_data),
        headers={**boss_headers, "Idempotency-Key": "abc"},
    )
    assert response.status_code == 400, response.text
    assert response.json()["code"] == "INVALID_IDEMPOTENCY_KEY"


async def test_failed_execution_releases_key(client, seed_data, boss_headers, fake_redis):
    """执行失败必须释放键，否则客户端用同一个 key 重试会一直拿到上次的错误。"""
    key = "test-key-release-0001"
    headers = {**boss_headers, "Idempotency-Key": key}
    payload = {
        "customer_id": seed_data["customer_id"],
        # 库存 10，买 99 必然不足
        "items": [{"part_id": seed_data["part_id"], "quantity": 99}],
    }

    failed = await client.post("/api/v1/sales/outbound", json=payload, headers=headers)
    assert failed.status_code == 409, failed.text
    assert failed.json()["code"] == "INSUFFICIENT_STOCK"

    # 键已释放，库存没有变化
    assert await fake_redis.exists(f"erp:idem:sales.outbound:{key}") == 0
    assert await _stock(client, seed_data["part_id"], boss_headers) == 10

    # 用同一个 key 重试一笔合法单据，能正常执行（不会被上次的错误卡住）
    retried = await client.post(
        "/api/v1/sales/outbound",
        json=_sale_payload(seed_data),
        headers=headers,
    )
    assert retried.status_code == 201, retried.text
    assert Decimal(retried.json()["total_amount"]) > Decimal("0")


async def test_purchase_inbound_is_idempotent(client, seed_data, boss_headers):
    key = "test-key-purchase-01"
    headers = {**boss_headers, "Idempotency-Key": key}
    payload = {
        "supplier_id": seed_data["supplier_id"],
        "items": [{"part_id": seed_data["part_id"], "quantity": 5, "price": "13.00"}],
    }

    first = await client.post("/api/v1/purchases/inbound", json=payload, headers=headers)
    second = await client.post("/api/v1/purchases/inbound", json=payload, headers=headers)
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert second.headers.get("idempotent-replay") == "true"
    assert second.json()["order_no"] == first.json()["order_no"]

    # 入库只加了一次：10 + 5
    assert await _stock(client, seed_data["part_id"], boss_headers) == 15
