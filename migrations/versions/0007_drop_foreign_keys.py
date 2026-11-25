"""drop all database foreign keys

Revision ID: 0007_drop_foreign_keys
Revises: 0006_restore_next_followup
Create Date: 2026-11-24

业务约定：表之间保留 id 关联和索引，但数据库不建外键；
关联完整性由应用层在写入/更新时维护。
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect

revision: str = "0007_drop_foreign_keys"
down_revision: str | None = "0006_restore_next_followup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    for table_name in inspector.get_table_names():
        for fk in inspector.get_foreign_keys(table_name):
            constraint_name = fk.get("name")
            if constraint_name:
                op.drop_constraint(constraint_name, table_name, type_="foreignkey")


def downgrade() -> None:
    # 外键清单取决于历史库实际结构，降级不自动重建；需要时由 DBA 按业务关系补回。
    pass
