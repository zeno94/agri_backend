"""农机配件主数据。"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import CheckConstraint, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, big_int_pk


class Part(TimestampMixin, Base):
    __tablename__ = "parts"
    __table_args__ = (
        CheckConstraint("stock >= 0", name="stock_non_negative"),
        CheckConstraint("safe_stock >= 0", name="safe_stock_non_negative"),
        CheckConstraint("purchase_price >= 0", name="purchase_price_non_negative"),
        CheckConstraint("sale_price >= 0", name="sale_price_non_negative"),
        Index("ix_parts_name", "name"),
        Index("ix_parts_category", "category"),
        Index("ix_parts_brand", "brand"),
    )

    id: Mapped[int] = mapped_column(big_int_pk(), primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False, comment="适配型号")
    category: Mapped[str] = mapped_column(String(50), nullable=False, comment="配件分类")
    brand: Mapped[str] = mapped_column(String(50), nullable=False, default="", server_default="", comment="品牌")

    stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0", comment="当前库存")
    safe_stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0", comment="安全库存")

    purchase_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00"), server_default="0.00", comment="采购参考价"
    )
    sale_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00"), server_default="0.00", comment="销售参考价"
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<Part id={self.id} name={self.name!r} stock={self.stock} safe_stock={self.safe_stock}>"
