"""restore next follow-up fields

Revision ID: 0006_restore_next_followup
Revises: 0005_customer_addresses
Create Date: 2026-11-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_restore_next_followup"
down_revision: str | None = "0005_customer_addresses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("customers") as batch:
        batch.add_column(sa.Column("next_follow_up_at", sa.DateTime(), nullable=True))
        batch.create_index("ix_customers_next_follow_up_at", ["next_follow_up_at"])

    with op.batch_alter_table("customer_followups") as batch:
        batch.add_column(sa.Column("next_follow_up_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("customer_followups") as batch:
        batch.drop_column("next_follow_up_at")

    with op.batch_alter_table("customers") as batch:
        batch.drop_index("ix_customers_next_follow_up_at")
        batch.drop_column("next_follow_up_at")
