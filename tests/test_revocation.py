"""JWT 吊销测试：登出、改密、停用账号后旧 Token 必须失效。"""

from __future__ import annotations

import asyncio


async def _login(client, username: str, password: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_logout_revokes_current_token(client, seed_data):
    headers = await _login(client, "staff", "Staff@123456")

    # 登出前可用
    ok = await client.get("/api/v1/auth/me", headers=headers)
    assert ok.status_code == 200, ok.text

    out = await client.post("/api/v1/auth/logout", headers=headers)
    assert out.status_code == 200, out.text

    # 登出后同一张 Token 立刻失效
    after = await client.get("/api/v1/auth/me", headers=headers)
    assert after.status_code == 401, after.text
    assert after.json()["code"] == "TOKEN_REVOKED"


async def test_login_again_after_logout_works(client, seed_data):
    """吊销的是那一张 Token，不是把账号封了——重新登录取到的新 Token 必须能用。"""
    old = await _login(client, "staff", "Staff@123456")
    await client.post("/api/v1/auth/logout", headers=old)

    again = await _login(client, "staff", "Staff@123456")
    response = await client.get("/api/v1/auth/me", headers=again)
    assert response.status_code == 200, response.text

    # 旧 Token 仍然是失效的，新 Token 不受影响
    stale = await client.get("/api/v1/auth/me", headers=old)
    assert stale.status_code == 401


async def test_reset_password_revokes_all_user_tokens(client, seed_data, boss_headers):
    employee = await _login(client, "staff", "Staff@123456")
    assert (await client.get("/api/v1/auth/me", headers=employee)).status_code == 200

    # JWT 的 iat 是秒级精度，水位比较需要跨过一个整秒边界才稳定
    await asyncio.sleep(1.05)

    reset = await client.post(
        f"/api/v1/users/{seed_data['employee_id']}/reset-password",
        json={"password": "NewPass@123456"},
        headers=boss_headers,
    )
    assert reset.status_code == 200, reset.text

    # 改密后旧 Token 失效
    stale = await client.get("/api/v1/auth/me", headers=employee)
    assert stale.status_code == 401, stale.text
    assert stale.json()["code"] == "TOKEN_REVOKED"

    # 新密码能登录，且拿到的 Token 可用
    fresh = await _login(client, "staff", "NewPass@123456")
    assert (await client.get("/api/v1/auth/me", headers=fresh)).status_code == 200


async def test_deactivate_user_revokes_tokens(client, seed_data, boss_headers):
    employee = await _login(client, "staff", "Staff@123456")

    updated = await client.patch(
        f"/api/v1/users/{seed_data['employee_id']}",
        json={"is_active": False},
        headers=boss_headers,
    )
    assert updated.status_code == 200, updated.text

    stale = await client.get("/api/v1/auth/me", headers=employee)
    assert stale.status_code in (401, 403), stale.text


async def test_unknown_jti_token_is_not_revoked(client, seed_data, boss_headers):
    """没有登出的正常 Token 不能被误判为吊销（防止把所有人都锁死在登录页）。"""
    for _ in range(3):
        headers = await _login(client, "boss", "Boss@123456")
        response = await client.get("/api/v1/auth/me", headers=headers)
        assert response.status_code == 200, response.text
