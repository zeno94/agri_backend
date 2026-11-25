"""客户主数据与客户跟进记录。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Index, Numeric, String, text
from sqlalchemy.dialects.mysql import JSON as MySQLJSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, big_int_pk

if TYPE_CHECKING:
    from app.models.sale import SaleOrder
    from app.models.user import User

# MySQL 使用原生 JSON；SQLite 测试环境退化为 TEXT 存储的 JSON。
JSONType = JSON().with_variant(MySQLJSON(), "mysql")


class Customer(TimestampMixin, Base):
    __tablename__ = "customers"
    __table_args__ = (
        Index("ix_customers_name", "name"),
        Index("ix_customers_phone", "phone"),
        Index("ix_customers_town_village", "town", "village"),
    )

    id: Mapped[int] = mapped_column(big_int_pk(), primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    city: Mapped[str] = mapped_column(
        String(50), nullable=False, default="开封市", server_default="开封市", comment="市"
    )
    county: Mapped[str] = mapped_column(
        String(50), nullable=False, default="杞县", server_default="杞县", comment="县/区"
    )
    town: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="乡镇")
    village: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="村")
    customer_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="其他", server_default="其他", comment="客户类型"
    )
    acreage: Mapped[Decimal | None] = mapped_column(Numeric(8, 1), nullable=True, comment="种植面积（亩）")
    main_crops: Mapped[list | None] = mapped_column(JSONType, nullable=True, comment="主要作物")
    tags: Mapped[list | None] = mapped_column(JSONType, nullable=True, comment="客户标签")
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_contact_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("1"))

    sale_orders: Mapped[list[SaleOrder]] = relationship(
        "SaleOrder",
        primaryjoin="Customer.id == foreign(SaleOrder.customer_id)",
        back_populates="customer",
    )
    followups: Mapped[list[CustomerFollowup]] = relationship(
        "CustomerFollowup",
        primaryjoin="Customer.id == foreign(CustomerFollowup.customer_id)",
        back_populates="customer",
        cascade="all, delete-orphan",
        order_by="CustomerFollowup.id.desc()",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Customer id={self.id} name={self.name!r}>"


class CustomerFollowup(Base):
    __tablename__ = "customer_followups"
    __table_args__ = (Index("ix_customer_followups_customer_created", "customer_id", "created_at"),)

    id: Mapped[int] = mapped_column(big_int_pk(), primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(big_int_pk(), nullable=False)
    operator_id: Mapped[int] = mapped_column(big_int_pk(), nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False, default="电话", server_default="电话")
    content: Mapped[str] = mapped_column(String(500), nullable=False)
    next_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))

    customer: Mapped[Customer] = relationship(
        "Customer",
        primaryjoin="foreign(CustomerFollowup.customer_id) == Customer.id",
        back_populates="followups",
    )
    operator: Mapped[User] = relationship(
        "User",
        primaryjoin="foreign(CustomerFollowup.operator_id) == User.id",
        lazy="joined",
    )
