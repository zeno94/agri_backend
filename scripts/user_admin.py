"""账号巡检与角色管理（运维工具）。

用途：
- 查看数据库里到底有哪些账号，以及每个账号的角色 / 启用状态 / 密码哈希类型；
- 修改账号角色（boss / employee）；
- 不修改密码（密码重置使用 scripts.reset_password）。

用法：
    python -m scripts.user_admin list
    python -m scripts.user_admin show --username staff01
    python -m scripts.user_admin set-role --username staff01 --role employee
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime

from sqlalchemy import select

from app.db.session import SessionLocal, dispose_engine
from app.models.enums import UserRole
from app.models.user import User

ROLE_DESCRIPTIONS = {
    UserRole.BOSS.value: "管理员：全部模块 + 用户管理 + 模块配置",
    UserRole.EMPLOYEE.value: "普通用户：只显示管理员分配的模块",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="查看/调整农机配件 ERP 账号。")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="列出全部账号")

    show_parser = subparsers.add_parser("show", help="查看单个账号详情")
    show_parser.add_argument("--username", required=True, help="登录账号")

    role_parser = subparsers.add_parser("set-role", help="修改账号角色")
    role_parser.add_argument("--username", required=True, help="登录账号")
    role_parser.add_argument(
        "--role",
        required=True,
        choices=[UserRole.BOSS.value, UserRole.EMPLOYEE.value],
        help="boss（老板）/ employee（员工）",
    )
    return parser.parse_args()


def _format_time(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _hash_hint(password_hash: str) -> str:
    """只展示哈希类型/长度，绝不打印完整哈希。"""
    if not password_hash:
        return "空（无法登录）"
    if password_hash.startswith(("$2a$", "$2b$", "$2y$")):
        return f"bcrypt（前缀 {password_hash[:7]}，长度 {len(password_hash)}）"
    if len(password_hash) == 32:
        return "32 位摘要，疑似 MD5（旧方案，当前验证必然失败）"
    if len(password_hash) == 40:
        return "40 位摘要，疑似 SHA1（旧方案，当前验证必然失败）"
    return f"非 bcrypt 格式（长度 {len(password_hash)}，前缀 {password_hash[:4]}...）"


def _print_user(user: User) -> None:
    role_desc = ROLE_DESCRIPTIONS.get(user.role, "未知角色")
    print(f"ID        : {user.id}")
    print(f"账号      : {user.username}")
    print(f"角色      : {user.role}（{role_desc}）")
    print(f"启用状态  : {'启用' if user.is_active else '停用（登录会返回 403 USER_DISABLED）'}")
    print(f"创建时间  : {_format_time(user.created_at)}（UTC）")
    print(f"密码哈希  : {_hash_hint(user.password_hash)}")


async def _list_users() -> int:
    async with SessionLocal() as db:
        users = (await db.scalars(select(User).order_by(User.id))).all()

    if not users:
        print("数据库中没有账号。请执行 `python -m app.db.init_db` 或 `scripts.reset_password --create`。")
        return 1

    print(f"{'ID':<6}{'USERNAME':<20}{'ROLE':<12}{'ACTIVE':<10}CREATED_AT(UTC)")
    for user in users:
        print(
            f"{user.id:<6}{user.username:<20}{user.role:<12}"
            f"{str(user.is_active):<10}{_format_time(user.created_at)}"
        )
    print("\n角色说明：boss = 管理员，全部模块；employee = 普通用户，按管理员分配模块。")
    return 0


async def _show_user(username: str) -> int:
    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.username == username))

    if user is None:
        print(f"账号不存在：{username}")
        print(
            "如需创建，可执行：\n"
            f"  python -m scripts.reset_password --username {username} "
            "--password '你的密码' --create --role employee --activate"
        )
        return 1

    _print_user(user)
    print(
        "\n提示：bcrypt 前缀只代表算法。若旧系统是「明文直接 bcrypt」而本项目是"
        "「SHA-256 预处理后 bcrypt」，同一个密码仍会校验失败；最稳妥是重置密码："
    )
    print(f"  python -m scripts.reset_password --username {username} --activate")
    return 0


async def _set_role(username: str, role: str) -> int:
    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.username == username))
        if user is None:
            print(f"账号不存在：{username}")
            return 1

        old_role = user.role
        user.role = role
        await db.commit()
        await db.refresh(user)

    print(f"已修改账号 {username} 的角色：{old_role} -> {user.role}")
    print(f"角色权限：{ROLE_DESCRIPTIONS.get(user.role, '未知角色')}")
    return 0


async def _main() -> int:
    args = _parse_args()
    try:
        if args.command == "list":
            return await _list_users()
        if args.command == "show":
            return await _show_user(args.username.strip())
        if args.command == "set-role":
            return await _set_role(args.username.strip(), args.role)
        raise SystemExit(f"未知命令：{args.command}")
    finally:
        await dispose_engine()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
