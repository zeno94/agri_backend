"""业务服务层统一出口。

Service 负责：事务边界、跨表业务规则、缓存失效、DTO 组装。
"""

from app.services import auth, dashboard, inventory, part, partner, purchase, sale

__all__ = ["auth", "dashboard", "inventory", "part", "partner", "purchase", "sale"]
