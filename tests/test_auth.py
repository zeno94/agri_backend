"""认证与权限测试。"""

from __future__ import annotations


async def test_login_success_returns_jwt_and_user(client, seed_data):
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "boss", "password": "Boss@123456"},
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
        json={"username": "boss", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_CREDENTIALS"


async def test_login_with_unknown_user_returns_401(client, seed_data):
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "not-exists", "password": "whatever"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_CREDENTIALS"


async def test_login_payload_validation_returns_422(client, seed_data):
    """JSON 缺少 password 时应返回参数校验错误，而不是 422 表单缺失字段的模糊报错。"""
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "boss"},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert any("password" in error["loc"] for error in body["detail"])


async def test_json_login_and_me(client, seed_data):
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "staff", "password": "Staff@123456"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "staff"
    assert me.json()["role"] == "employee"


async def test_form_login_endpoint_remains_available_for_swagger(client, seed_data):
    """Swagger Authorize 仍走 OAuth2 表单端点。"""
    response = await client.post(
        "/api/v1/auth/login/form",
        data={"username": "boss", "password": "Boss@123456"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["access_token"]
    assert response.json()["user"]["username"] == "boss"


async def test_legacy_json_login_path_still_works(client, seed_data):
    """旧前端可能仍调用 /auth/login/json，保留兼容。"""
    response = await client.post(
        "/api/v1/auth/login/json",
        json={"username": "staff", "password": "Staff@123456"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["access_token"]


async def test_openapi_contract_for_login_and_write_endpoints(client):
    """契约测试：业务写接口必须是 JSON，只有 Swagger 表单登录是表单。"""
    schema = (await client.get("/openapi.json")).json()

    json_operations = [
        ("/api/v1/auth/login", "post"),
        ("/api/v1/auth/login/json", "post"),
        ("/api/v1/parts", "post"),
        ("/api/v1/parts/{part_id}", "put"),
        ("/api/v1/suppliers", "post"),
        ("/api/v1/customers", "post"),
        ("/api/v1/purchases/inbound", "post"),
        ("/api/v1/sales/outbound", "post"),
    ]
    for path, method in json_operations:
        content = schema["paths"][path][method].get("requestBody", {}).get("content", {})
        assert "application/json" in content, f"{method.upper()} {path} 未声明 JSON 请求体"

    form_content = schema["paths"]["/api/v1/auth/login/form"]["post"]["requestBody"]["content"]
    assert "application/x-www-form-urlencoded" in form_content

    token_url = schema["components"]["securitySchemes"]["OAuth2PasswordBearer"]["flows"]["password"]["tokenUrl"]
    assert token_url == "/api/v1/auth/login/form"


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
