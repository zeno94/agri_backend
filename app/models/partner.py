"""往来单位（供应商 / 客户）。"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, big_int_pk
from app.models.enums import PartnerType


class Partner(TimestampMixin, Base):
    __tablename__ = "partners"
    __table_args__ = (
        CheckConstraint("type IN ('supplier', 'customer')", name="type"),
    )

    id: Mapped[int] = mapped_column(big_int_pk(), primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=PartnerType.CUSTOMER.value,
        server_default=PartnerType.CUSTOMER.value,
    )
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<Partner id={self.id} name={self.name!r} type={self.type!r}>"
