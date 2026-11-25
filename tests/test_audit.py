"""操作审计日志与数据范围权限测试。"""

from __future__ import annotations

import json


async def test_login_success_and_failure_are_audited(client, seed_data, boss_headers):
    failed = await client.post(
        "/api/v1/auth/login",
        json={"username": "boss", "password": "wrong-password"},
    )
    assert failed.status_code == 401

    response = await client.get(
        "/api/v1/audit/logs",
        params={"action": "auth.login_failed", "page_size": 50},
        headers=boss_headers,
    )
    assert response.status_code == 200, response.text
    logs = response.json()["items"]
    assert logs, "登录失败应写入审计日志"
    assert logs[0]["success"] is False
    assert logs[0]["status_code"] == 401
    assert logs[0]["action"] == "auth.login_failed"
    # 审计明细绝不能包含密码
    assert "wrong-password" not in json.dumps(logs[0]["detail"], ensure_ascii=False)

    login_logs = await client.get(
        "/api/v1/audit/logs",
        params={"action": "auth.login", "page_size": 50},
        headers=boss_headers,
    )
    assert any(item["username"] == "boss" for item in login_logs.json()["items"])


async def test_employee_only_sees_own_audit_logs(client, seed_data, boss_headers, employee_headers):
    purchase = await client.post(
        "/api/v1/purchases/inbound",
        json={
            "supplier_id": seed_data["supplier_id"],
            "items": [{"part_id": seed_data["part_id"], "quantity": 2, "price": "12.00"}],
        },
        headers=employee_headers,
    )
    assert purchase.status_code == 201, purchase.text

    employee_logs = await client.get(
        "/api/v1/audit/logs",
        params={"page_size": 100},
        headers=employee_headers,
    )
    assert employee_logs.status_code == 200, employee_logs.text
    employee_items = employee_logs.json()["items"]
    assert employee_items
    assert all(item["user_id"] == seed_data["employee_id"] for item in employee_items)
    assert all(item["username"] == "staff" for item in employee_items)

    boss_logs = await client.get(
        "/api/v1/audit/logs",
        params={"page_size": 100},
        headers=boss_headers,
    )
    assert boss_logs.status_code == 200
    assert any(item["username"] == "boss" for item in boss_logs.json()["items"])
    assert any(item["username"] == "staff" for item in boss_logs.json()["items"])

    forbidden = await client.get(
        "/api/v1/audit/logs",
        params={"username": "boss"},
        headers=employee_headers,
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "FORBIDDEN"


async def test_employee_cannot_read_other_users_audit_detail(client, seed_data, boss_headers, employee_headers):
    boss_logs = await client.get(
        "/api/v1/audit/logs",
        params={"username": "boss", "page_size": 100},
        headers=boss_headers,
    )
    assert boss_logs.status_code == 200
    boss_log_id = boss_logs.json()["items"][0]["id"]

    detail = await client.get(f"/api/v1/audit/logs/{boss_log_id}", headers=employee_headers)
    assert detail.status_code == 404
    assert detail.json()["code"] == "AUDIT_LOG_NOT_FOUND"

    own_logs = await client.get(
        "/api/v1/audit/logs",
        params={"page_size": 100},
        headers=employee_headers,
    )
    own_log_id = own_logs.json()["items"][0]["id"]
    own_detail = await client.get(f"/api/v1/audit/logs/{own_log_id}", headers=employee_headers)
    assert own_detail.status_code == 200


async def test_business_action_and_failure_are_audited(client, seed_data, boss_headers, employee_headers):
    sale = await client.post(
        "/api/v1/sales/outbound",
        json={
            "customer_id": seed_data["customer_id"],
            "part_id": seed_data["part_id"],
            "quantity": 2,
        },
        headers=employee_headers,
    )
    assert sale.status_code == 201, sale.text
    order_no = sale.json()["order_no"]

    logs = await client.get(
        "/api/v1/audit/logs",
        params={"action": "sale.outbound", "page_size": 50},
        headers=boss_headers,
    )
    assert logs.status_code == 200
    sale_logs = [item for item in logs.json()["items"] if item["success"]]
    assert any(item["detail"].get("order_no") == order_no for item in sale_logs)

    # 员工不能改成交价；失败也应留痕
    override = await client.post(
        "/api/v1/sales/outbound",
        json={
            "customer_id": seed_data["customer_id"],
            "part_id": seed_data["part_id"],
            "quantity": 1,
            "price": "1.00",
        },
        headers=employee_headers,
    )
    assert override.status_code == 403
    assert override.json()["code"] == "PRICE_OVERRIDE_FORBIDDEN"

    failed_logs = await client.get(
        "/api/v1/audit/logs",
        params={"action": "sale.outbound", "success": "false", "page_size": 50},
        headers=boss_headers,
    )
    assert any(item["error_code"] == "PRICE_OVERRIDE_FORBIDDEN" for item in failed_logs.json()["items"])


async def test_boss_can_override_sale_price(client, seed_data, boss_headers):
    response = await client.post(
        "/api/v1/sales/outbound",
        json={
            "customer_id": seed_data["customer_id"],
            "part_id": seed_data["part_id"],
            "quantity": 1,
            "price": "19.90",
        },
        headers=boss_headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["items"][0]["price"] == "19.90"


async def test_boss_part_create_is_audited(client, seed_data, boss_headers):
    created = await client.post(
        "/api/v1/parts",
        json={
            "name": "审计测试配件",
            "model": "AUDIT-1",
            "brand": "测试",
            "category": "测试",
            "stock": 1,
            "safe_stock": 0,
            "purchase_price": "5.00",
            "sale_price": "9.90",
        },
        headers=boss_headers,
    )
    assert created.status_code == 201, created.text

    logs = await client.get(
        "/api/v1/audit/logs",
        params={"action": "part.create", "page_size": 20},
        headers=boss_headers,
    )
    assert any(item["resource_id"] == created.json()["id"] for item in logs.json()["items"])


async def test_permission_denial_is_audited(client, seed_data, employee_headers, boss_headers):
    denied = await client.put(
        f"/api/v1/parts/{seed_data['part_id']}",
        json={"sale_price": "1.00"},
        headers=employee_headers,
    )
    assert denied.status_code == 403

    logs = await client.get(
        "/api/v1/audit/logs",
        params={"action": "authz.denied", "page_size": 20},
        headers=boss_headers,
    )
    assert logs.status_code == 200
    items = logs.json()["items"]
    assert any(
        item["error_code"] == "FORBIDDEN" and item["path"] == f"/api/v1/parts/{seed_data['part_id']}" for item in items
    )
