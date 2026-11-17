"""CRUD 数据访问层统一出口。

约定：
- 只负责「取数 / 写对象」，不 commit；
- 事务边界、跨表业务规则放在 services 层。
"""

from app.crud import dashboard, inventory, order, part, partner, user

__all__ = ["dashboard", "inventory", "order", "part", "partner", "user"]
