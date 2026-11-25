"""销售单及销售明细。"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, big_int_pk
from app.models.enums import OrderStatus

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.part import Part
    from app.models.user import User


class SaleOrder(TimestampMixin, Base):
    __tablename__ = "sale_orders"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'completed')", name="status"),
        Index("ix_sale_orders_status_created_at", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(big_int_pk(), primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(big_int_pk(), nullable=False, index=True)
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=Decimal("0.00"), server_default="0.00"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=OrderStatus.PENDING.value,
        server_default=OrderStatus.PENDING.value,
    )
    operator_id: Mapped[int] = mapped_column(big_int_pk(), nullable=False, index=True)
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)

    customer: Mapped[Customer] = relationship(
        "Customer",
        primaryjoin="foreign(SaleOrder.customer_id) == Customer.id",
        back_populates="sale_orders",
        lazy="joined",
    )
    operator: Mapped[User] = relationship(
        "User",
        primaryjoin="foreign(SaleOrder.operator_id) == User.id",
        lazy="joined",
    )
    items: Mapped[list[SaleItem]] = relationship(
        "SaleItem",
        primaryjoin="SaleOrder.id == foreign(SaleItem.order_id)",
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="SaleItem.id",
    )


class SaleItem(Base):
    __tablename__ = "sale_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("price >= 0", name="price_non_negative"),
        Index("ix_sale_items_order_id", "order_id"),
        Index("ix_sale_items_part_id", "part_id"),
    )

    id: Mapped[int] = mapped_column(big_int_pk(), primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(big_int_pk(), nullable=False)
    part_id: Mapped[int] = mapped_column(big_int_pk(), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    order: Mapped[SaleOrder] = relationship(
        "SaleOrder",
        primaryjoin="foreign(SaleItem.order_id) == SaleOrder.id",
        back_populates="items",
    )
    part: Mapped[Part] = relationship(
        "Part",
        primaryjoin="foreign(SaleItem.part_id) == Part.id",
        lazy="joined",
    )
