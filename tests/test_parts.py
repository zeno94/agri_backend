"""配件管理、缓存与库存预警测试。"""

from __future__ import annotations

from decimal import Decimal

from app.models.part import Part


async def test_parts_pagination_and_filters(client, seed_data, boss_headers):
    page = await client.get(
        "/api/v1/parts",
        params={"page": 1, "size": 1},
        headers=boss_headers,
    )
    assert page.status_code == 200
    body = page.json()
    assert body["total"] == 2
    assert body["pages"] == 2
    assert len(body["items"]) == 1

    by_name = await client.get(
        "/api/v1/parts",
        params={"name": "滤清"},
        headers=boss_headers,
    )
    assert by_name.json()["total"] == 1
    assert by_name.json()["items"][0]["name"] == "柴油滤清器"

    by_category = await client.get(
        "/api/v1/parts",
        params={"category": "植保配件"},
        headers=boss_headers,
    )
    assert by_category.json()["total"] == 1
    assert by_category.json()["items"][0]["name"] == "植保机喷头"

    no_match = await client.get(
        "/api/v1/parts",
        params={"name": "不存在的配件"},
        headers=boss_headers,
    )
    assert no_match.json()["total"] == 0
    assert no_match.json()["pages"] == 0


async def test_parts_list_is_cached_and_invalidated(
    client, seed_data, boss_headers, fake_redis, session_factory
):
    params = {"page": 1, "size": 20, "name": "柴油"}

    first = await client.get("/api/v1/parts", params=params, headers=boss_headers)
    assert first.json()["total"] == 1

    cache_keys = await fake_redis.keys("erp:parts:list:*")
    assert cache_keys, "首次查询应写入 Redis 缓存"

    # 绕过接口直接写库：不触发缓存版本变更，再次查询应仍命中旧缓存
    async with session_factory() as session:
        session.add(
            Part(
                name="柴油滤清器（副厂）",
                model="4L88-F",
                category="滤清器",
                brand="副厂",
                stock=1,
                safe_stock=1,
                purchase_price=Decimal("10.00"),
                sale_price=Decimal("20.00"),
            )
        )
        await session.commit()

    second = await client.get("/api/v1/parts", params=params, headers=boss_headers)
    assert second.json()["total"] == 1, "缓存未过期时应直接命中 Redis，而不是回源数据库"

    # 通过接口新增配件 -> 缓存版本自增 -> 旧缓存失效
    created = await client.post(
        "/api/v1/parts",
        json={
            "name": "刹车片",
            "model": "SF-1",
            "category": "制动系统",
            "brand": "时风",
            "stock": 0,
            "safe_stock": 0,
            "purchase_price": "5.00",
            "sale_price": "10.00",
        },
        headers=boss_headers,
    )
    assert created.status_code == 201, created.text

    third = await client.get("/api/v1/parts", params=params, headers=boss_headers)
    assert third.json()["total"] == 2, "缓存失效后应回源数据库，读到直接插入的数据"


async def test_create_part_writes_opening_stock_log(client, seed_data, boss_headers):
    created = await client.post(
        "/api/v1/parts",
        json={
            "name": "收割机刀片",
            "model": "KUBOTA-01",
            "category": "收割机配件",
            "brand": "久保田",
            "stock": 7,
            "safe_stock": 3,
            "purchase_price": "30.00",
            "sale_price": "60.00",
        },
        headers=boss_headers,
    )
    assert created.status_code == 201, created.text
    part_id = created.json()["id"]
    assert created.json()["stock"] == 7

    logs = await client.get(
        "/api/v1/inventory/logs",
        params={"part_id": part_id},
        headers=boss_headers,
    )
    assert logs.status_code == 200
    body = logs.json()
    assert body["total"] == 1
    log = body["items"][0]
    assert log["change_type"] == "check"
    assert log["change_qty"] == 7
    assert log["before_stock"] == 0
    assert log["after_stock"] == 7
    assert log["operator_id"] == seed_data["boss_id"]


async def test_update_part_and_stock_adjustment_log(client, seed_data, boss_headers):
    part_id = seed_data["part_id"]

    updated = await client.put(
        f"/api/v1/parts/{part_id}",
        json={"sale_price": "28.00", "stock": 4},
        headers=boss_headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["sale_price"] == "28.00"
    assert updated.json()["stock"] == 4

    logs = await client.get(
        "/api/v1/inventory/logs",
        params={"part_id": part_id},
        headers=boss_headers,
    )
    assert logs.json()["total"] == 1
    log = logs.json()["items"][0]
    assert log["change_type"] == "check"
    assert log["change_qty"] == -6
    assert log["before_stock"] == 10
    assert log["after_stock"] == 4


async def test_warning_lists_parts_below_safe_stock(client, seed_data, boss_headers):
    response = await client.get("/api/v1/parts/warning", headers=boss_headers)

    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["name"] == "植保机喷头"
    assert items[0]["stock"] == 2
    assert items[0]["safe_stock"] == 10
    assert items[0]["shortage"] == 8


async def test_part_validation_errors(client, seed_data, boss_headers):
    negative_price = await client.post(
        "/api/v1/parts",
        json={
            "name": "异常配件",
            "model": "X",
            "category": "测试",
            "brand": "测试",
            "stock": 1,
            "safe_stock": 1,
            "purchase_price": "-1.00",
            "sale_price": "10.00",
        },
        headers=boss_headers,
    )
    assert negative_price.status_code == 422
    assert negative_price.json()["code"] == "VALIDATION_ERROR"

    empty_update = await client.put(
        f"/api/v1/parts/{seed_data['part_id']}",
        json={},
        headers=boss_headers,
    )
    assert empty_update.status_code == 422
    assert empty_update.json()["code"] == "VALIDATION_ERROR"
