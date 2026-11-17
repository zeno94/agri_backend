"""SQLAlchemy 声明式基类、命名约定与公共列类型。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, Integer, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# 统一的约束命名，保证 Alembic 生成的迁移在不同环境下名称稳定
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def utcnow() -> datetime:
    """数据库统一存储 naive UTC 时间，展示时由前端按本地时区转换。"""
    return datetime.now(UTC).replace(tzinfo=None)


def big_int_pk() -> BigInteger:
    """MySQL 使用 BIGINT；SQLite（单元测试）自动降级为 INTEGER 以支持自增主键。"""
    return BigInteger().with_variant(Integer, "sqlite")


class TimestampMixin:
    """创建/更新时间（应用侧写入 UTC，同时保留数据库默认值兜底）。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow,
        server_default=func.now(),
        comment="创建时间（UTC）",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        server_default=func.now(),
        comment="更新时间（UTC）",
    )
