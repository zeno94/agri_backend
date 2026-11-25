"""add dynamic modules and user module assignments

Revision ID: 0004_modules
Revises: 0003_split_partners
Create Date: 2026-11-24
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from app.db.module_defaults import DEFAULT_EMPLOYEE_MODULES, DEFAULT_MODULES

revision: str = "0004_modules"
down_revision: str | None = "0003_split_partners"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    user_id_type: sa.types.TypeEngine = sa.Integer()
    if "users" in inspector.get_table_names():
        for column in inspector.get_columns("users"):
            if column["name"] == "id":
                user_id_type = column["type"]
                break

    op.create_table(
        "modules",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("path", sa.String(length=100), nullable=False),
        sa.Column("icon", sa.String(length=50), server_default="Grid", nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("is_admin_only", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_modules")),
    )
    with op.batch_alter_table("modules") as batch:
        batch.create_index(op.f("ix_modules_code"), ["code"], unique=True)
        batch.create_index(op.f("ix_modules_path"), ["path"], unique=True)

    op.create_table(
        "user_modules",
        sa.Column("user_id", user_id_type, nullable=False),
        sa.Column("module_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.ForeignKeyConstraint(["module_id"], ["modules.id"], name=op.f("fk_user_modules_module_id_modules"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_user_modules_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "module_id", name=op.f("pk_user_modules")),
    )
    with op.batch_alter_table("user_modules") as batch:
        batch.create_index(op.f("ix_user_modules_user_id"), ["user_id"])
        batch.create_index(op.f("ix_user_modules_module_id"), ["module_id"])

    now = datetime(2026, 11, 24, 0, 0, 0)
    module_table = sa.table(
        "modules",
        sa.column("id", sa.Integer()),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("path", sa.String()),
        sa.column("icon", sa.String()),
        sa.column("description", sa.String()),
        sa.column("sort_order", sa.Integer()),
        sa.column("is_active", sa.Boolean()),
        sa.column("is_admin_only", sa.Boolean()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    op.bulk_insert(
        module_table,
        [
            {
                "id": index,
                "code": item["code"],
                "name": item["name"],
                "path": item["path"],
                "icon": item["icon"],
                "description": item.get("description"),
                "sort_order": item["sort_order"],
                "is_active": True,
                "is_admin_only": item["is_admin_only"],
                "created_at": now,
                "updated_at": now,
            }
            for index, item in enumerate(DEFAULT_MODULES, start=1)
        ],
    )

    # 现有员工按默认业务模块授权；管理员走 role 直接放行。
    op.execute(
        f"""
        INSERT INTO user_modules (user_id, module_id)
        SELECT u.id, m.id
        FROM users u CROSS JOIN modules m
        WHERE u.role = 'employee'
          AND m.code IN ({", ".join("'" + code + "'" for code in DEFAULT_EMPLOYEE_MODULES)})
          AND NOT EXISTS (
              SELECT 1 FROM user_modules um WHERE um.user_id = u.id AND um.module_id = m.id
          )
        """
    )


def downgrade() -> None:
    op.drop_table("user_modules")
    op.drop_table("modules")
