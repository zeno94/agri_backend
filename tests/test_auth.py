"""认证与权限测试。"""

from __future__ import annotations


async def test_login_success_returns_jwt_and_user(client, seed_data):
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "boss", "password": "Boss@123456"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0
    assert body["user"]["username"] == "boss"
    assert body["user"]["role"] == "boss"


async def test_login_with_wrong_password_returns_401(client, seed_data):
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "boss", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_CREDENTIALS"


async def test_login_with_unknown_user_returns_401(client, seed_data):
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "not-exists", "password": "whatever"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_CREDENTIALS"


async def test_json_login_and_me(client, seed_data):
    login = await client.post(
        "/api/v1/auth/login/json",
        json={"username": "staff", "password": "Staff@123456"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "staff"
    assert me.json()["role"] == "employee"


async def test_protected_endpoint_requires_token(client, seed_data):
    response = await client.get("/api/v1/parts")

    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "NOT_AUTHENTICATED"
    assert response.headers.get("www-authenticate") == "Bearer"


async def test_employee_is_forbidden_from_dashboard(client, seed_data, employee_headers):
    response = await client.get("/api/v1/dashboard", headers=employee_headers)

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


async def test_health_check(client):
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
