"""业务服务层统一出口。

Service 负责：事务边界、跨表业务规则、缓存失效、DTO 组装。
"""

from app.services import (
    audit,
    auth,
    customer,
    dashboard,
    inventory,
    module,
    part,
    purchase,
    sale,
    supplier,
    user,
)

__all__ = [
    "audit",
    "auth",
    "customer",
    "dashboard",
    "inventory",
    "module",
    "part",
    "purchase",
    "sale",
    "supplier",
    "user",
]
