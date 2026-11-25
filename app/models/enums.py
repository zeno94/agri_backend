"""业务枚举。

数据库中使用 VARCHAR 存储枚举值（配合 CHECK 约束），
相比 MySQL 原生 ENUM 更易扩展、迁移更平滑。
"""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    """员工角色：老板 / 普通员工。"""

    BOSS = "boss"
    EMPLOYEE = "employee"


class OrderStatus(StrEnum):
    """单据状态。

    本期所有入库/出库在创建时即完成（completed）；
    保留 pending 以支持后续「草稿单 / 待审核」流程。
    """

    PENDING = "pending"
    COMPLETED = "completed"


class ChangeType(StrEnum):
    """库存变动类型：采购入库 / 销售出库 / 盘点调整。"""

    IN = "in"
    OUT = "out"
    CHECK = "check"
