"""customer city/county fields and remove next follow-up

Revision ID: 0005_customer_addresses
Revises: 0004_modules
Create Date: 2026-11-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_customer_addresses"
down_revision: str | None = "0004_modules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("customers") as batch:
        batch.add_column(
            sa.Column("city", sa.String(length=50), server_default="开封市", nullable=False)
        )
        batch.add_column(
            sa.Column("county", sa.String(length=50), server_default="杞县", nullable=False)
        )
        batch.drop_column("next_follow_up_at")
        batch.create_index("ix_customers_city_county", ["city", "county"])

    with op.batch_alter_table("customer_followups") as batch:
        batch.drop_column("next_follow_up_at")


def downgrade() -> None:
    with op.batch_alter_table("customer_followups") as batch:
        batch.add_column(sa.Column("next_follow_up_at", sa.DateTime(), nullable=True))

    with op.batch_alter_table("customers") as batch:
        batch.drop_index("ix_customers_city_county")
        batch.add_column(sa.Column("next_follow_up_at", sa.DateTime(), nullable=True))
        batch.drop_column("county")
        batch.drop_column("city")
