"""供应商主数据。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Index, Integer, String, text
from sqlalchemy.dialects.mysql import JSON as MySQLJSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base, TimestampMixin, big_int_pk

if TYPE_CHECKING:
    from app.models.purchase import PurchaseOrder

JSONType = JSON().with_variant(MySQLJSON(), "mysql")


class Supplier(TimestampMixin, Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        Index("ix_suppliers_name", "name"),
        Index("ix_suppliers_phone", "phone"),
    )

    id: Mapped[int] = mapped_column(big_int_pk(), primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    address: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_person: Mapped[str | None] = mapped_column(String(50), nullable=True)
    main_categories: Mapped[list | None] = mapped_column(JSONType, nullable=True, comment="主营品类")
    delivery_days: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="送货天数")
    payment_terms: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="结算方式")
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("1"))

    purchase_orders: Mapped[list[PurchaseOrder]] = relationship(
        "PurchaseOrder",
        primaryjoin="Supplier.id == foreign(PurchaseOrder.supplier_id)",
        back_populates="supplier",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Supplier id={self.id} name={self.name!r}>"
