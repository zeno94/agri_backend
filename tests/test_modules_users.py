"""用户创建、模块分配与模块开关测试。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


async def _login(client, username: str, password: str) -> dict[str, str]:
    response = await client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_admin_creates_user_and_assigns_modules(client, seed_data, boss_headers):
    created = await client.post(
        "/api/v1/users",
        json={
            "username": "staff02",
            "password": "Staff02@123",
            "module_codes": ["parts", "sales"],
        },
        headers=boss_headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["role"] == "employee"
    assert {m["code"] for m in body["modules"]} == {"parts", "sales"}

    headers = await _login(client, "staff02", "Staff02@123")
    assert (await client.get("/api/v1/parts", headers=headers)).status_code == 200
    assert (await client.get("/api/v1/sales", headers=headers)).status_code == 200
    denied = await client.get("/api/v1/purchases", headers=headers)
    assert denied.status_code == 403
    assert denied.json()["code"] == "FORBIDDEN"

    updated = await client.put(
        f"/api/v1/users/{body['id']}/modules",
        json={"module_codes": ["parts"]},
        headers=boss_headers,
    )
    assert updated.status_code == 200, updated.text
    assert {m["code"] for m in updated.json()["modules"]} == {"parts"}
    assert (await client.get("/api/v1/sales", headers=headers)).status_code == 403


async def test_admin_can_disable_module_and_employee_loses_access(client, seed_data, boss_headers, employee_headers):
    assert (await client.get("/api/v1/audit/logs", headers=employee_headers)).status_code == 200
    audit_module_id = seed_data["module_ids"]["audit"]

    disabled = await client.put(
        f"/api/v1/modules/{audit_module_id}",
        json={"is_active": False},
        headers=boss_headers,
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["is_active"] is False
    denied = await client.get("/api/v1/audit/logs", headers=employee_headers)
    assert denied.status_code == 403

    restored = await client.put(
        f"/api/v1/modules/{audit_module_id}",
        json={"is_active": True},
        headers=boss_headers,
    )
    assert restored.status_code == 200
    assert (await client.get("/api/v1/audit/logs", headers=employee_headers)).status_code == 200


async def test_customer_detail_and_followup(client, seed_data, boss_headers):
    detail = await client.get(f"/api/v1/customers/{seed_data['customer_id']}", headers=boss_headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["town"] == "邢口镇"
    assert body["stats"]["order_count"] == 0
    assert body["followups"] == []

    next_at = datetime.now(UTC) + timedelta(days=7)
    followup = await client.post(
        f"/api/v1/customers/{seed_data['customer_id']}/followups",
        json={
            "method": "电话",
            "content": "麦收前提醒备刀片",
            "next_follow_up_at": next_at.isoformat(),
        },
        headers=boss_headers,
    )
    assert followup.status_code == 201, followup.text
    assert followup.json()["content"] == "麦收前提醒备刀片"
    assert followup.json()["operator_name"] == "boss"

    updated = await client.get(f"/api/v1/customers/{seed_data['customer_id']}", headers=boss_headers)
    assert updated.status_code == 200
    assert len(updated.json()["followups"]) == 1
    assert updated.json()["next_follow_up_at"] is not None
    assert updated.json()["followups"][0]["next_follow_up_at"] is not None


async def test_supplier_management_and_customer_management_lists(client, seed_data, boss_headers):
    suppliers = await client.get("/api/v1/suppliers", headers=boss_headers)
    assert suppliers.status_code == 200, suppliers.text
    assert suppliers.json()["total"] == 1
    assert suppliers.json()["items"][0]["main_categories"] == ["传动带", "轴承"]

    customers = await client.get("/api/v1/customers", headers=boss_headers)
    assert customers.status_code == 200, customers.text
    assert customers.json()["total"] == 1
    assert customers.json()["items"][0]["stats"]["order_count"] == 0


async def test_warning_module_can_read_warning_only(client, seed_data, boss_headers):
    created = await client.post(
        "/api/v1/users",
        json={
            "username": "warning_only",
            "password": "Warning@123",
            "module_codes": ["warning"],
        },
        headers=boss_headers,
    )
    assert created.status_code == 201, created.text
    headers = await _login(client, "warning_only", "Warning@123")

    warning = await client.get("/api/v1/parts/warning", headers=headers)
    assert warning.status_code == 200, warning.text
    parts = await client.get("/api/v1/parts", headers=headers)
    assert parts.status_code == 403


async def test_customer_list_sorted_by_last_purchase(client, seed_data, boss_headers):
    created = await client.post(
        "/api/v1/customers",
        json={"name": "没有订单的客户", "phone": "13803789999"},
        headers=boss_headers,
    )
    assert created.status_code == 201, created.text

    sale = await client.post(
        "/api/v1/sales/outbound",
        json={
            "customer_id": seed_data["customer_id"],
            "items": [{"part_id": seed_data["part_id"], "quantity": 1}],
        },
        headers=boss_headers,
    )
    assert sale.status_code == 201, sale.text

    response = await client.get("/api/v1/customers", params={"size": 10}, headers=boss_headers)
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert items[0]["name"] == "王建军"
    assert items[-1]["name"] == "没有订单的客户"
