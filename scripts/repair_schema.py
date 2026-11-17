"""修复历史数据库与当前 ORM 模型的结构差异（只增不减）。

典型场景：数据库由旧版本代码 / 手写 SQL / 旧数据卷创建，缺少后来新增的列，
应用启动后查询报 MySQL 1054 Unknown column（例如 users.is_active）。

本工具会：
1. 补建缺失的表；
2. 为已有表补上模型中定义但数据库缺失的列（先可空、回填、再改 NOT NULL）；
3. 补建缺失的索引（含唯一索引）；
4. 可选地把没有 alembic_version 的库标记为当前 head。

安全边界：
- 只做 ADD COLUMN / ADD INDEX / CREATE TABLE，不删除列、不改列类型、不迁移业务数据；
- 仅支持 MySQL 8.0（本项目生产数据库）；
- 复杂结构差异（主键/外键/字段类型不一致）仍需人工迁移或重建数据库；
- 执行前请备份；建议停服或低峰执行。

用法：
    python -m scripts.repair_schema                # 只检查并打印修复计划（dry-run）
    python -m scripts.repair_schema --apply        # 执行修复
    python -m scripts.repair_schema --apply --stamp-head  # 修复后标记 Alembic head
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Connection, Dialect, make_url
from sqlalchemy.sql.elements import TextClause
from sqlalchemy.sql.functions import Function

import app.models  # noqa: F401  # 注册全部模型元数据
from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.db.base import Base
from app.db.session import dispose_engine, engine

logger = get_logger("scripts.repair_schema")

LEGACY_ORDER_PREFIX = {"purchase_orders": "PO", "sale_orders": "SO"}


def _quote(conn: Connection, identifier: str) -> str:
    return conn.dialect.identifier_preparer.quote(identifier)


def _render_default(column: sa.Column, dialect: Dialect) -> str | None:
    """渲染列默认值；MySQL 的 DATETIME 必须用 CURRENT_TIMESTAMP，不能是 now()。"""
    if column.server_default is None:
        return None

    arg = column.server_default.arg
    if isinstance(arg, TextClause):
        return str(arg)
    if isinstance(arg, Function):
        if isinstance(column.type, sa.DateTime):
            return "CURRENT_TIMESTAMP"
        return str(arg.compile(dialect=dialect))
    if isinstance(arg, str):
        return "'" + arg.replace("'", "''") + "'"
    return str(arg)


def _column_definition(conn: Connection, column: sa.Column, *, nullable: bool) -> str:
    """生成 MySQL 的列定义片段（用于 ADD COLUMN / MODIFY COLUMN）。"""
    parts = [f"{_quote(conn, column.name)} {column.type.compile(dialect=conn.dialect)}"]
    parts.append("NULL" if nullable else "NOT NULL")

    default = _render_default(column, conn.dialect)
    if default is not None:
        parts.append(f"DEFAULT {default}")

    if column.comment:
        comment = column.comment.replace("'", "''")
        parts.append(f"COMMENT '{comment}'")
    return " ".join(parts)


def _fallback_literal(column: sa.Column) -> str | None:
    """NOT NULL 且无默认值的列，回填历史行时使用的兜底值。"""
    if isinstance(column.type, sa.Boolean):
        return "1" if column.name == "is_active" else "0"
    if isinstance(column.type, sa.Integer | sa.BigInteger | sa.SmallInteger):
        return "0"
    if isinstance(column.type, sa.Numeric):
        return "0.00"
    if isinstance(column.type, sa.DateTime):
        return "CURRENT_TIMESTAMP"
    if isinstance(column.type, sa.String | sa.Text):
        return "''"
    return None


def _missing_indexes(inspector: sa.Inspector, table: sa.Table) -> list[sa.Index]:
    """按「名称或列组合」判断索引是否已存在，避免历史库不同名字导致重复建索引。"""
    existing = inspector.get_indexes(table.name)
    existing_names = {item["name"] for item in existing}
    existing_signatures = {
        (tuple(item["column_names"]), bool(item["unique"])) for item in existing
    }

    missing: list[sa.Index] = []
    for index in table.indexes:
        signature = (tuple(column.name for column in index.columns), bool(index.unique))
        if index.name in existing_names or signature in existing_signatures:
            continue
        missing.append(index)
    return missing


def _inspect_plan(conn: Connection) -> dict[str, object]:
    """对比数据库与模型，返回缺失表 / 列 / 索引。"""
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())
    plan: dict[str, object] = {
        "missing_tables": [],
        "missing_columns": {},
        "missing_indexes": {},
    }

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            plan["missing_tables"].append(table.name)  # type: ignore[union-attr]
            continue

        existing_columns = {column["name"] for column in inspector.get_columns(table.name)}
        missing_columns = [column for column in table.columns if column.name not in existing_columns]
        if missing_columns:
            plan["missing_columns"][table.name] = missing_columns  # type: ignore[index]

        missing_indexes = _missing_indexes(inspector, table)
        if missing_indexes:
            plan["missing_indexes"][table.name] = missing_indexes  # type: ignore[index]

    return plan


def _print_plan(plan: dict[str, object]) -> None:
    missing_tables = plan["missing_tables"]
    missing_columns: dict[str, list[sa.Column]] = plan["missing_columns"]  # type: ignore[assignment]
    missing_indexes: dict[str, list[sa.Index]] = plan["missing_indexes"]  # type: ignore[assignment]

    if not missing_tables and not missing_columns and not missing_indexes:
        print("数据库结构与当前模型一致，无需修复。")
        return

    if missing_tables:
        print("缺失表：")
        for name in missing_tables:  # type: ignore[union-attr]
            print(f"  - {name}")

    if missing_columns:
        print("缺失字段：")
        for table_name, columns in missing_columns.items():
            names = ", ".join(f"{column.name}({column.type})" for column in columns)
            print(f"  - {table_name}: {names}")

    if missing_indexes:
        print("缺失索引：")
        for table_name, indexes in missing_indexes.items():
            names = ", ".join(str(index.name) for index in indexes)
            print(f"  - {table_name}: {names}")


def _add_missing_columns(conn: Connection, missing_columns: dict[str, list[sa.Column]]) -> int:
    """先以可空方式加列，避免已有数据行导致 NOT NULL 失败。"""
    count = 0
    for table_name, columns in missing_columns.items():
        for column in columns:
            sql = (
                f"ALTER TABLE {_quote(conn, table_name)} "
                f"ADD COLUMN {_column_definition(conn, column, nullable=True)}"
            )
            conn.execute(sa.text(sql))
            count += 1
            logger.info("新增字段 %s.%s", table_name, column.name)
    return count


def _backfill_missing_values(
    conn: Connection,
    missing_columns: dict[str, list[sa.Column]],
) -> None:
    """为 NOT NULL 列回填历史行；业务特殊列（单号/库存快照）做专门回填。"""
    for table_name, columns in missing_columns.items():
        column_names = {column.name for column in columns}
        quoted_table = _quote(conn, table_name)

        # 单号：旧库没有 order_no，用主键生成唯一值
        if table_name in LEGACY_ORDER_PREFIX and "order_no" in column_names:
            prefix = LEGACY_ORDER_PREFIX[table_name]
            quoted_column = _quote(conn, "order_no")
            conn.execute(
                sa.text(
                    f"UPDATE {quoted_table} "
                    f"SET {quoted_column} = CONCAT('{prefix}-LEGACY-', id) "
                    f"WHERE {quoted_column} IS NULL"
                )
            )
            logger.info("回填 %s.order_no 为 %s-LEGACY-<id>", table_name, prefix)

        # 库存快照：以当前零件库存为 after_stock，反推 before_stock
        if table_name == "inventory_logs" and column_names & {"before_stock", "after_stock"}:
            conn.execute(
                sa.text(
                    f"UPDATE {quoted_table} l "
                    "JOIN parts p ON p.id = l.part_id "
                    "SET l.after_stock = COALESCE(l.after_stock, p.stock), "
                    "    l.before_stock = COALESCE(l.before_stock, p.stock - l.change_qty) "
                    "WHERE l.before_stock IS NULL OR l.after_stock IS NULL"
                )
            )
            # 兜底：极少数孤立流水（零件已被物理删除）也必须有值
            conn.execute(
                sa.text(
                    f"UPDATE {quoted_table} SET after_stock = COALESCE(after_stock, 0) "
                    "WHERE after_stock IS NULL"
                )
            )
            conn.execute(
                sa.text(
                    f"UPDATE {quoted_table} "
                    "SET before_stock = COALESCE(before_stock, after_stock, 0) "
                    "WHERE before_stock IS NULL"
                )
            )
            logger.info("回填 %s 的 before_stock / after_stock", table_name)

        for column in columns:
            if column.nullable:
                continue
            if table_name in LEGACY_ORDER_PREFIX and column.name == "order_no":
                continue
            if table_name == "inventory_logs" and column.name in {"before_stock", "after_stock"}:
                continue

            fallback = _fallback_literal(column)
            if fallback is None:
                raise RuntimeError(
                    f"无法为 {table_name}.{column.name} 生成兜底值，请手工迁移该表"
                )
            quoted_column = _quote(conn, column.name)
            conn.execute(
                sa.text(
                    f"UPDATE {quoted_table} SET {quoted_column} = {fallback} "
                    f"WHERE {quoted_column} IS NULL"
                )
            )


def _enforce_not_null(conn: Connection, missing_columns: dict[str, list[sa.Column]]) -> int:
    """回填完成后，把非空列改为 NOT NULL。"""
    count = 0
    for table_name, columns in missing_columns.items():
        for column in columns:
            if column.nullable:
                continue
            sql = (
                f"ALTER TABLE {_quote(conn, table_name)} "
                f"MODIFY COLUMN {_column_definition(conn, column, nullable=False)}"
            )
            conn.execute(sa.text(sql))
            count += 1
            logger.info("字段 %s.%s 设置为 NOT NULL", table_name, column.name)
    return count


def _create_missing_indexes(conn: Connection) -> int:
    """补建模型声明的索引；唯一索引若因历史重复数据失败，只告警不终止。"""
    count = 0
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        for index in _missing_indexes(inspector, table):
            try:
                index.create(conn, checkfirst=True)
            except sa.exc.SQLAlchemyError as exc:
                logger.error("创建索引 %s 失败（可能存在重复数据）：%s", index.name, exc)
                continue
            count += 1
            logger.info("新增索引 %s", index.name)
    return count


def _stamp_head(conn: Connection) -> None:
    """把没有 Alembic 版本记录的旧库标记为当前 head，避免后续 upgrade 重复建表。"""
    ini_path = Path(__file__).resolve().parent.parent / "alembic.ini"
    script = ScriptDirectory.from_config(Config(str(ini_path)))
    head = script.get_current_head()
    if head is None:
        raise RuntimeError("未找到 Alembic head revision")

    conn.execute(
        sa.text(
            "CREATE TABLE IF NOT EXISTS alembic_version ("
            "version_num VARCHAR(32) NOT NULL, "
            "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
        )
    )
    current = conn.execute(sa.text("SELECT version_num FROM alembic_version LIMIT 1")).scalar()
    if current is None:
        conn.execute(
            sa.text("INSERT INTO alembic_version (version_num) VALUES (:version)"),
            {"version": head},
        )
        print(f"已将数据库标记为 Alembic head：{head}")
    else:
        print(f"alembic_version 已存在（{current}），未覆盖。")


def _sync_schema(conn: Connection, *, apply: bool, stamp_head: bool) -> int:
    dialect_name = conn.dialect.name
    if dialect_name != "mysql":
        raise SystemExit(
            "该修复脚本仅支持 MySQL。SQLite 开发库请删除数据库文件后执行 "
            "`alembic upgrade head` 重建。"
        )

    plan = _inspect_plan(conn)
    _print_plan(plan)

    missing_tables: list[str] = plan["missing_tables"]  # type: ignore[assignment]
    missing_columns: dict[str, list[sa.Column]] = plan["missing_columns"]  # type: ignore[assignment]
    missing_indexes: dict[str, list[sa.Index]] = plan["missing_indexes"]  # type: ignore[assignment]

    if not missing_tables and not missing_columns and not missing_indexes:
        if stamp_head:
            _stamp_head(conn)
        return 0

    if not apply:
        print("\n当前为 dry-run，未修改数据库。确认后追加 --apply 执行修复。")
        return 0

    if missing_tables:
        print("\n补建缺失表...")
        Base.metadata.create_all(conn, checkfirst=True)

    added_columns = 0
    if missing_columns:
        print("\n补建缺失字段（先可空，回填后再改 NOT NULL）...")
        added_columns = _add_missing_columns(conn, missing_columns)
        _backfill_missing_values(conn, missing_columns)
        _enforce_not_null(conn, missing_columns)

    print("\n补建缺失索引...")
    added_indexes = _create_missing_indexes(conn)

    print(
        f"\n修复完成：补建表 {len(missing_tables)} 张，"
        f"补建字段 {added_columns} 个，补建索引 {added_indexes} 个。"
    )

    if stamp_head:
        _stamp_head(conn)
    else:
        inspector = sa.inspect(conn)
        if not inspector.has_table("alembic_version"):
            print(
                "\n提示：数据库中不存在 alembic_version 表。"
                "如后续使用 Alembic，请执行 `alembic stamp head`，"
                "或重新运行本脚本并追加 --stamp-head。"
            )
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="补建 MySQL 缺失的表/字段/索引，修复 Unknown column 1054 错误。",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="真正执行修复；默认只打印计划（dry-run）。",
    )
    parser.add_argument(
        "--stamp-head",
        action="store_true",
        help="修复后若没有 alembic_version，则标记为当前 head。",
    )
    args = parser.parse_args()
    if args.stamp_head and not args.apply:
        parser.error("--stamp-head 必须与 --apply 一起使用")
    return args


async def _main() -> None:
    args = _parse_args()
    setup_logging()

    backend = make_url(settings.DATABASE_URL).get_backend_name()
    if backend != "mysql":
        raise SystemExit(
            f"当前 DATABASE_URL 使用 {backend}，修复脚本仅支持 MySQL。"
            "SQLite 请删除数据库文件后重新执行 alembic upgrade head。"
        )

    safe_url = make_url(settings.DATABASE_URL).render_as_string(hide_password=True)
    print(f"目标数据库：{safe_url}")
    print("警告：执行前请备份数据库，并尽量停服/低峰操作。\n")

    try:
        async with engine.begin() as conn:
            await conn.run_sync(
                _sync_schema,
                apply=args.apply,
                stamp_head=args.stamp_head,
            )
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(_main())
