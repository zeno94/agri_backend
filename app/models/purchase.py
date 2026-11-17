"""采购单及采购明细。"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, big_int_pk
from app.models.enums import OrderStatus

if TYPE_CHECKING:
    from app.models.part import Part
    from app.models.partner import Partner
    from app.models.user import User


class PurchaseOrder(TimestampMixin, Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'completed')", name="status"),
        Index("ix_purchase_orders_status_created_at", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(big_int_pk(), primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    partner_id: Mapped[int] = mapped_column(
        big_int_pk(), ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00"), server_default="0.00"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=OrderStatus.PENDING.value,
        server_default=OrderStatus.PENDING.value,
    )
    operator_id: Mapped[int] = mapped_column(
        big_int_pk(), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)

    partner: Mapped[Partner] = relationship(lazy="joined")
    operator: Mapped[User] = relationship(lazy="joined")
    items: Mapped[list[PurchaseItem]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="PurchaseItem.id",
    )


class PurchaseItem(Base):
    __tablename__ = "purchase_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("price >= 0", name="price_non_negative"),
        Index("ix_purchase_items_order_id", "order_id"),
        Index("ix_purchase_items_part_id", "part_id"),
    )

    id: Mapped[int] = mapped_column(big_int_pk(), primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        big_int_pk(), ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False
    )
    part_id: Mapped[int] = mapped_column(big_int_pk(), ForeignKey("parts.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    order: Mapped[PurchaseOrder] = relationship(back_populates="items")
    part: Mapped[Part] = relationship(lazy="joined")
