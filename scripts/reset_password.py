"""重置已有账号密码，或在账号不存在时创建账号（运维工具）。

使用场景：
- 旧数据库中的账号密码哈希来自其他系统/其他哈希方案，当前登录逻辑无法校验；
- 初始化脚本已经跑过，但不知道该账号的密码；
- 需要临时启用一个被停用的账号。

安全说明：
- 不传 --password 时使用交互式输入（不回显、不进入 shell history）；
- 密码至少 8 位；
- 重置后使用当前项目的 SHA-256 + bcrypt 方案重新计算哈希；
- 本工具只应由运维在服务器/容器内执行。

用法：
    python -m scripts.reset_password --username admin
    python -m scripts.reset_password --username admin --password 'Boss@123456' --activate
    python -m scripts.reset_password --username admin --password 'Boss@123456' --create --role boss
"""

from __future__ import annotations

import argparse
import asyncio
import getpass

from sqlalchemy import select

from app.core.logging import setup_logging
from app.core.security import hash_password, verify_password
from app.db.session import SessionLocal, dispose_engine
from app.models.enums import UserRole
from app.models.user import User

MIN_PASSWORD_LENGTH = 8


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="重置农机配件 ERP 账号密码；账号不存在时可选择创建。",
    )
    parser.add_argument("--username", required=True, help="登录账号")
    parser.add_argument(
        "--password",
        default=None,
        help="新密码；不传则交互式输入。直接传参会留在 shell history，生产建议不传。",
    )
    parser.add_argument(
        "--create",
        action="store_true",
        help="账号不存在时创建（默认 boss 角色，可用 --role 指定）",
    )
    parser.add_argument(
        "--role",
        choices=[UserRole.BOSS.value, UserRole.EMPLOYEE.value],
        default=UserRole.BOSS.value,
        help="配合 --create 使用，默认 boss",
    )
    parser.add_argument(
        "--activate",
        action="store_true",
        help="同时把已有账号置为启用状态（is_active=true）",
    )
    return parser.parse_args()


def _read_password(provided: str | None) -> str:
    if provided is not None:
        password = provided
    else:
        password = getpass.getpass(f"请输入新密码（至少 {MIN_PASSWORD_LENGTH} 位）: ")
        confirm = getpass.getpass("请再次输入新密码: ")
        if password != confirm:
            raise SystemExit("两次输入的密码不一致")

    if len(password) < MIN_PASSWORD_LENGTH:
        raise SystemExit(f"密码长度不能少于 {MIN_PASSWORD_LENGTH} 位")
    return password


async def _reset(username: str, password: str, *, create: bool, role: str, activate: bool) -> int:
    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.username == username))

        if user is None:
            if not create:
                print(f"用户不存在：{username}")
                print(
                    "可加 --create 直接创建，或先执行 `python -m app.db.init_db` 初始化示例账号。"
                )
                return 1

            user = User(
                username=username,
                password_hash=hash_password(password),
                role=role,
                is_active=True,
            )
            db.add(user)
            action = "创建"
        else:
            user.password_hash = hash_password(password)
            if activate:
                user.is_active = True
            action = "重置"

        await db.flush()

        # 写库前自检，避免因哈希实现异常导致新密码也不可用
        if not verify_password(password, user.password_hash):
            raise RuntimeError("密码哈希自检失败，未写入数据库")

        await db.commit()
        await db.refresh(user)

    print(f"已{action}账号：{username}")
    print(f"用户 ID：{user.id}，角色：{user.role}，启用：{user.is_active}")
    if not user.is_active:
        print("提示：账号当前为停用状态，登录会返回 403；可追加 --activate 重新执行。")
    return 0


async def _main() -> int:
    args = _parse_args()
    setup_logging()

    username = args.username.strip()
    if not username:
        raise SystemExit("用户名不能为空")

    password = _read_password(args.password)
    try:
        return await _reset(
            username,
            password,
            create=args.create,
            role=args.role,
            activate=args.activate,
        )
    finally:
        await dispose_engine()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
