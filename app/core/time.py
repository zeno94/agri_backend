"""业务时区日期边界工具。

数据库统一存储 naive UTC；对外筛选日期使用业务时区（默认 Asia/Shanghai），
避免“北京时间凌晨的单据被算到前一天”这类跨时区错位。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from app.core.config import settings


def local_day_start(value: date) -> datetime:
    """业务时区某天 00:00 对应的 UTC naive 时间。"""
    local = datetime.combine(value, time.min, tzinfo=settings.tzinfo)
    return local.astimezone(UTC).replace(tzinfo=None)


def local_day_end_exclusive(value: date) -> datetime:
    """业务时区某天结束后的 00:00（右开区间）对应的 UTC naive 时间。"""
    local = datetime.combine(value + timedelta(days=1), time.min, tzinfo=settings.tzinfo)
    return local.astimezone(UTC).replace(tzinfo=None)


def to_local_date(value: datetime) -> date:
    """把数据库里的 naive UTC 时间转成业务时区日期。"""
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value
    return aware.astimezone(settings.tzinfo).date()
