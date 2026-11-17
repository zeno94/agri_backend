"""库存变动流水（审计日志）。

change_qty 采用带符号数量：入库为正、出库为负、盘点为调整差额，
配合 before_stock / after_stock 可完整复盘任意时点的库存。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, big_int_pk, utcnow
from app.models.enums import ChangeType

if TYPE_CHECKING:
    from app.models.part import Part
    from app.models.user import User


class InventoryLog(Base):
    __tablename__ = "inventory_logs"
    __table_args__ = (
        CheckConstraint("change_type IN ('in', 'out', 'check')", name="change_type"),
        Index("ix_inventory_logs_part_created_at", "part_id", "created_at"),
        Index("ix_inventory_logs_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(big_int_pk(), primary_key=True, autoincrement=True)
    part_id: Mapped[int] = mapped_column(big_int_pk(), ForeignKey("parts.id", ondelete="RESTRICT"), nullable=False)
    change_type: Mapped[str] = mapped_column(String(10), nullable=False, default=ChangeType.CHECK.value)
    change_qty: Mapped[int] = mapped_column(Integer, nullable=False, comment="带符号变动数量：入正出负")
    before_stock: Mapped[int] = mapped_column(Integer, nullable=False, comment="变动前库存")
    after_stock: Mapped[int] = mapped_column(Integer, nullable=False, comment="变动后库存")
    operator_id: Mapped[int] = mapped_column(
        big_int_pk(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, server_default=func.now()
    )

    part: Mapped[Part] = relationship(lazy="joined")
    operator: Mapped[User] = relationship(lazy="joined")
