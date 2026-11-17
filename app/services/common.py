"""服务层公共工具。"""

from __future__ import annotations


def calc_pages(total: int, size: int) -> int:
    """总页数（向上取整）。"""
    if total <= 0:
        return 0
    return (total + size - 1) // size
