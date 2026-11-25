"""split partners into customers and suppliers

Revision ID: 0003_split_partners
Revises: 0002_audit_logs
Create Date: 2026-11-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0003_split_partners"
down_revision: str | None = "0002_audit_logs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    user_id_type: sa.types.TypeEngine = sa.Integer()
    if "users" in inspector.get_table_names():
        for column in inspector.get_columns("users"):
            if column["name"] == "id":
                user_id_type = column["type"]
                break

    def _fk_name(table: str, column: str) -> str:
        for fk in inspector.get_foreign_keys(table):
            if fk.get("constrained_columns") == [column]:
                return fk["name"]
        raise RuntimeError(f"{table}.{column} 外键不存在")

    def _index_name(table: str, column: str) -> str:
        for index in inspector.get_indexes(table):
            if index.get("column_names") == [column]:
                return index["name"]
        raise RuntimeError(f"{table}.{column} 索引不存在")

    sale_partner_fk = _fk_name("sale_orders", "partner_id")
    sale_partner_index = _index_name("sale_orders", "partner_id")
    purchase_partner_fk = _fk_name("purchase_orders", "partner_id")
    purchase_partner_index = _index_name("purchase_orders", "partner_id")

    op.create_table(
        "customers",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("town", sa.String(length=50), nullable=True),
        sa.Column("village", sa.String(length=50), nullable=True),
        sa.Column("customer_type", sa.String(length=30), server_default="其他", nullable=False),
        sa.Column("acreage", sa.Numeric(precision=8, scale=1), nullable=True),
        sa.Column("main_crops", sa.JSON(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("last_contact_at", sa.DateTime(), nullable=True),
        sa.Column("next_follow_up_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customers")),
    )
    with op.batch_alter_table("customers") as batch:
        batch.create_index(op.f("ix_customers_name"), ["name"])
        batch.create_index(op.f("ix_customers_phone"), ["phone"])
        batch.create_index("ix_customers_town_village", ["town", "village"])

    op.create_table(
        "suppliers",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("address", sa.String(length=200), nullable=True),
        sa.Column("contact_person", sa.String(length=50), nullable=True),
        sa.Column("main_categories", sa.JSON(), nullable=True),
        sa.Column("delivery_days", sa.Integer(), nullable=True),
        sa.Column("payment_terms", sa.String(length=100), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_suppliers")),
    )
    with op.batch_alter_table("suppliers") as batch:
        batch.create_index(op.f("ix_suppliers_name"), ["name"])
        batch.create_index(op.f("ix_suppliers_phone"), ["phone"])

    op.create_table(
        "customer_followups",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), autoincrement=True, nullable=False),
        sa.Column("customer_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("operator_id", user_id_type, nullable=False),
        sa.Column("method", sa.String(length=20), server_default="电话", nullable=False),
        sa.Column("content", sa.String(length=500), nullable=False),
        sa.Column("next_follow_up_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name=op.f("fk_customer_followups_customer_id_customers"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["operator_id"], ["users.id"], name=op.f("fk_customer_followups_operator_id_users"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customer_followups")),
    )
    with op.batch_alter_table("customer_followups") as batch:
        batch.create_index("ix_customer_followups_customer_created", ["customer_id", "created_at"])
        batch.create_index(op.f("ix_customer_followups_operator_id"), ["operator_id"])

    # 复制主数据：保留原 ID，订单回填不需要重映射。
    op.execute(
        """
        INSERT INTO suppliers (id, name, phone, address, contact_person, main_categories,
                               delivery_days, payment_terms, note, is_active, created_at, updated_at)
        SELECT id, name, phone, NULL, NULL, NULL, NULL, NULL, NULL, 1, created_at, updated_at
        FROM partners WHERE type = 'supplier'
        """
    )
    op.execute(
        """
        INSERT INTO customers (id, name, phone, town, village, customer_type, acreage,
                               main_crops, tags, note, is_active, created_at, updated_at)
        SELECT id, name, phone, NULL, NULL, '其他', NULL, NULL, NULL, NULL, 1, created_at, updated_at
        FROM partners WHERE type = 'customer'
        """
    )

    with op.batch_alter_table("sale_orders") as batch:
        batch.add_column(
            sa.Column(
                "customer_id",
                sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
                nullable=True,
            )
        )
    op.execute("UPDATE sale_orders SET customer_id = partner_id")

    with op.batch_alter_table("purchase_orders") as batch:
        batch.add_column(
            sa.Column(
                "supplier_id",
                sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
                nullable=True,
            )
        )
    op.execute("UPDATE purchase_orders SET supplier_id = partner_id")

    with op.batch_alter_table("sale_orders") as batch:
        batch.alter_column("customer_id", existing_type=sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False)
        batch.drop_constraint(sale_partner_fk, type_="foreignkey")
        batch.drop_index(sale_partner_index)
        batch.drop_column("partner_id")
        batch.create_index(op.f("ix_sale_orders_customer_id"), ["customer_id"])
        batch.create_foreign_key(
            op.f("fk_sale_orders_customer_id_customers"),
            "customers",
            ["customer_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    with op.batch_alter_table("purchase_orders") as batch:
        batch.alter_column("supplier_id", existing_type=sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False)
        batch.drop_constraint(purchase_partner_fk, type_="foreignkey")
        batch.drop_index(purchase_partner_index)
        batch.drop_column("partner_id")
        batch.create_index(op.f("ix_purchase_orders_supplier_id"), ["supplier_id"])
        batch.create_foreign_key(
            op.f("fk_purchase_orders_supplier_id_suppliers"),
            "suppliers",
            ["supplier_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    # 审计详情里旧的 partner_id/partner_name 按销售/采购动作改名为 customer/supplier。
    bind = op.get_bind()
    if bind.dialect.name == "mysql":
        op.execute(
            """
            UPDATE audit_logs
            SET detail = JSON_SET(
                JSON_REMOVE(detail, '$.partner_id', '$.partner_name'),
                '$.customer_id', JSON_EXTRACT(detail, '$.partner_id'),
                '$.customer_name', JSON_UNQUOTE(JSON_EXTRACT(detail, '$.partner_name'))
            )
            WHERE action = 'sale.outbound' AND detail IS NOT NULL
              AND JSON_EXTRACT(detail, '$.partner_id') IS NOT NULL
            """
        )
        op.execute(
            """
            UPDATE audit_logs
            SET detail = JSON_SET(
                JSON_REMOVE(detail, '$.partner_id', '$.partner_name'),
                '$.supplier_id', JSON_EXTRACT(detail, '$.partner_id'),
                '$.supplier_name', JSON_UNQUOTE(JSON_EXTRACT(detail, '$.partner_name'))
            )
            WHERE action = 'purchase.inbound' AND detail IS NOT NULL
              AND JSON_EXTRACT(detail, '$.partner_id') IS NOT NULL
            """
        )
        op.execute(
            """
            UPDATE audit_logs SET action = 'customer.create'
            WHERE action = 'partner.create'
              AND JSON_UNQUOTE(JSON_EXTRACT(detail, '$.type')) = 'customer'
            """
        )
        op.execute(
            """
            UPDATE audit_logs SET action = 'supplier.create'
            WHERE action = 'partner.create'
              AND JSON_UNQUOTE(JSON_EXTRACT(detail, '$.type')) = 'supplier'
            """
        )

    op.drop_table("partners")


def downgrade() -> None:
    # 重建 partners；原 ID 在两表中可能冲突，降级仅用于开发环境。
    op.create_table(
        "partners",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("type", sa.String(length=20), server_default="customer", nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_partners")),
    )
    with op.batch_alter_table("partners") as batch:
        batch.create_index(op.f("ix_partners_name"), ["name"])

    op.execute(
        "INSERT INTO partners (id, name, type, phone, created_at, updated_at) "
        "SELECT id, name, 'supplier', phone, created_at, updated_at FROM suppliers"
    )
    op.execute(
        "INSERT INTO partners (id, name, type, phone, created_at, updated_at) "
        "SELECT id, name, 'customer', phone, created_at, updated_at FROM customers"
    )

    with op.batch_alter_table("sale_orders") as batch:
        batch.add_column(sa.Column("partner_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True))
    op.execute("UPDATE sale_orders SET partner_id = customer_id")
    with op.batch_alter_table("sale_orders") as batch:
        batch.alter_column("partner_id", existing_type=sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False)
        batch.drop_constraint(op.f("fk_sale_orders_customer_id_customers"), type_="foreignkey")
        batch.drop_index(op.f("ix_sale_orders_customer_id"))
        batch.drop_column("customer_id")
        batch.create_index("ix_sale_orders_partner_id", ["partner_id"])
        batch.create_foreign_key("fk_sale_orders_partner_id_partners", "partners", ["partner_id"], ["id"], ondelete="RESTRICT")

    with op.batch_alter_table("purchase_orders") as batch:
        batch.add_column(sa.Column("partner_id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True))
    op.execute("UPDATE purchase_orders SET partner_id = supplier_id")
    with op.batch_alter_table("purchase_orders") as batch:
        batch.alter_column("partner_id", existing_type=sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False)
        batch.drop_constraint(op.f("fk_purchase_orders_supplier_id_suppliers"), type_="foreignkey")
        batch.drop_index(op.f("ix_purchase_orders_supplier_id"))
        batch.drop_column("supplier_id")
        batch.create_index("ix_purchase_orders_partner_id", ["partner_id"])
        batch.create_foreign_key("fk_purchase_orders_partner_id_partners", "partners", ["partner_id"], ["id"], ondelete="RESTRICT")

    op.drop_table("customer_followups")
    op.drop_table("suppliers")
    op.drop_table("customers")
