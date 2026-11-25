"""角色权限矩阵测试：boss 管主数据，employee 做业务。"""

from __future__ import annotations

from decimal import Decimal


async def test_employee_cannot_create_or_update_parts(client, seed_data, employee_headers):
    create = await client.post(
        "/api/v1/parts",
        json={
            "name": "员工越权配件",
            "model": "NO-AUTH",
            "brand": "测试",
            "category": "测试",
            "stock": 1,
            "safe_stock": 1,
            "purchase_price": "1.00",
            "sale_price": "2.00",
        },
        headers=employee_headers,
    )
    assert create.status_code == 403
    assert create.json()["code"] == "FORBIDDEN"

    update = await client.put(
        f"/api/v1/parts/{seed_data['part_id']}",
        json={"sale_price": "99.00"},
        headers=employee_headers,
    )
    assert update.status_code == 403
    assert update.json()["code"] == "FORBIDDEN"

    # 原值未被修改
    part = await client.get(f"/api/v1/parts/{seed_data['part_id']}", headers=employee_headers)
    assert part.json()["sale_price"] == "25.00"


async def test_employee_cannot_create_supplier(client, seed_data, employee_headers, boss_headers):
    payload = {"name": "员工越权供应商", "phone": "13800000000"}
    response = await client.post("/api/v1/suppliers", json=payload, headers=employee_headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"

    # boss 仍可正常新增
    allowed = await client.post("/api/v1/suppliers", json=payload, headers=boss_headers)
    assert allowed.status_code == 201, allowed.text


async def test_employee_can_create_customer_when_module_assigned(client, seed_data, employee_headers):
    response = await client.post(
        "/api/v1/customers",
        json={"name": "李女士（傅集镇周庄村）", "phone": "19903780299", "town": "傅集镇"},
        headers=employee_headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["name"] == "李女士（傅集镇周庄村）"


async def test_employee_can_read_master_data(client, seed_data, employee_headers):
    endpoints = [
        "/api/v1/parts",
        "/api/v1/parts/warning",
        "/api/v1/suppliers/options",
        "/api/v1/customers/options",
        "/api/v1/customers",
        "/api/v1/inventory/logs",
        "/api/v1/purchases",
        "/api/v1/sales",
        "/api/v1/audit/logs",
    ]
    for endpoint in endpoints:
        response = await client.get(endpoint, headers=employee_headers)
        assert response.status_code == 200, f"{endpoint}: {response.text}"


async def test_employee_can_purchase_and_sale(client, seed_data, employee_headers):
    purchase = await client.post(
        "/api/v1/purchases/inbound",
        json={
            "supplier_id": seed_data["supplier_id"],
            "items": [{"part_id": seed_data["part_id"], "quantity": 4, "price": "12.00"}],
        },
        headers=employee_headers,
    )
    assert purchase.status_code == 201, purchase.text
    assert purchase.json()["operator_name"] == "staff"

    sale = await client.post(
        "/api/v1/sales/outbound",
        json={
            "customer_id": seed_data["customer_id"],
            "items": [{"part_id": seed_data["part_id"], "quantity": 2}],
        },
        headers=employee_headers,
    )
    assert sale.status_code == 201, sale.text
    assert sale.json()["operator_name"] == "staff"
    assert Decimal(sale.json()["total_amount"]) == Decimal("50.00")

    part = await client.get(f"/api/v1/parts/{seed_data['part_id']}", headers=employee_headers)
    assert part.json()["stock"] == 12


async def test_employee_cannot_read_admin_modules(client, seed_data, employee_headers):
    for endpoint in ("/api/v1/suppliers", "/api/v1/users", "/api/v1/modules"):
        response = await client.get(endpoint, headers=employee_headers)
        assert response.status_code == 403, f"{endpoint}: {response.text}"
