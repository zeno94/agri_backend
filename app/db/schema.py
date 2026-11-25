"""启动时数据库结构预检。

AUTO_CREATE_TABLES / create_all 只会“建不存在的表”，不会给已有表补列。
一旦数据库比模型旧，请求期才会报 MySQL 1054 Unknown column，排查成本高。
这里在启动阶段快速比对表/列，发现漂移立即失败并给出可执行的修复命令。
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.engine import Connection

import app.models  # noqa: F401  # 确保单独调用本模块时 ORM 元数据已注册
from app.core.logging import get_logger
from app.db.base import Base
from app.db.session import engine

logger = get_logger(__name__)


def _find_missing_schema_parts(conn: Connection) -> list[str]:
    if not Base.metadata.tables:
        raise RuntimeError("ORM 元数据为空，无法执行结构预检")

    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())
    missing: list[str] = []

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            missing.append(f"{table.name}（整表）")
            continue

        existing_columns = {column["name"] for column in inspector.get_columns(table.name)}
        missing.extend(f"{table.name}.{column.name}" for column in table.columns if column.name not in existing_columns)
    return missing


async def find_schema_drift() -> list[str]:
    """返回缺失的表/字段列表；空列表表示结构一致。"""
    async with engine.connect() as conn:
        return await conn.run_sync(_find_missing_schema_parts)


async def ensure_schema_up_to_date() -> None:
    """启动预检：结构漂移时 fail-fast，并提示修复方式。"""
    missing = await find_schema_drift()
    if not missing:
        logger.info("数据库结构检查通过")
        return

    preview = ", ".join(missing[:12])
    suffix = " ..." if len(missing) > 12 else ""
    logger.error("数据库结构落后于代码，缺少 %s 项：%s%s", len(missing), preview, suffix)
    raise RuntimeError(
        f"数据库结构落后于代码，缺少 {len(missing)} 个字段/表：{preview}{suffix}。"
        "请先执行 `alembic upgrade head`；如果是旧库/旧数据卷，先 dry-run 运行 "
        "`python -m scripts.repair_schema`，确认后再加 `--apply` 修复。"
    )
