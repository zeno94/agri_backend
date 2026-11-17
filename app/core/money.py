"""金额与单号工具。金额统一使用 Decimal，避免浮点误差。"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def money(value: Decimal | int | str) -> Decimal:
    """将金额规整为两位小数（四舍五入），返回 Decimal。"""
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def generate_order_no(prefix: str) -> str:
    """生成业务单号，例如 PO20261117170301A1B2C3。"""
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"{prefix}{timestamp}{secrets.token_hex(3).upper()}"
