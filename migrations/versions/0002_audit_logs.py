"""add audit logs

Revision ID: 0002_audit_logs
Revises: e84dfb4282a0
Create Date: 2026-11-18

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "0002_audit_logs"
down_revision: str | None = "e84dfb4282a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 兼容 AUTO_CREATE_TABLES=true 的本地库：应用可能已按模型建过 audit_logs，
    # 此时跳过建表，但仍把 Alembic 版本推进到 0002。
    inspector = inspect(op.get_bind())
    if "audit_logs" in inspector.get_table_names():
        return

    # 历史库的 users.id 可能是 INT，新库是 BIGINT；外键两列类型必须完全一致，
    # 否则 MySQL 报 3780。这里按实际 users.id 类型创建 user_id。
    user_id_type: sa.types.TypeEngine = sa.BigInteger()
    if "users" in inspector.get_table_names():
        for column in inspector.get_columns("users"):
            if column["name"] == "id":
                user_id_type = column["type"]
                break

    op.create_table(
        "audit_logs",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "user_id",
            user_id_type,
            nullable=True,
        ),
        sa.Column("username", sa.String(length=50), server_default="", nullable=False),
        sa.Column("role", sa.String(length=20), server_default="", nullable=False),
        sa.Column(
            "action",
            sa.String(length=50),
            nullable=False,
            comment="业务动作，如 sale.outbound",
        ),
        sa.Column("module", sa.String(length=30), server_default="", nullable=False),
        sa.Column("resource_type", sa.String(length=30), nullable=True),
        sa.Column(
            "resource_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            nullable=True,
        ),
        sa.Column("method", sa.String(length=10), nullable=True),
        sa.Column("path", sa.String(length=255), nullable=True),
        sa.Column("status_code", sa.Integer(), server_default="200", nullable=False),
        sa.Column("success", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("error_code", sa.String(length=50), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_audit_logs_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    with op.batch_alter_table("audit_logs", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_audit_logs_user_id"), ["user_id"], unique=False
        )
        batch_op.create_index(
            "ix_audit_logs_user_created_at", ["user_id", "created_at"], unique=False
        )
        batch_op.create_index(
            "ix_audit_logs_action_created_at", ["action", "created_at"], unique=False
        )
        batch_op.create_index(
            "ix_audit_logs_created_at", ["created_at"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("audit_logs", schema=None) as batch_op:
        batch_op.drop_index("ix_audit_logs_created_at")
        batch_op.drop_index("ix_audit_logs_action_created_at")
        batch_op.drop_index("ix_audit_logs_user_created_at")
        batch_op.drop_index(batch_op.f("ix_audit_logs_user_id"))

    op.drop_table("audit_logs")
