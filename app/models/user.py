"""用户（员工 / 老板）。"""

from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, big_int_pk
from app.models.enums import UserRole


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('boss', 'employee')", name="role"),
    )

    id: Mapped[int] = mapped_column(big_int_pk(), primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=UserRole.EMPLOYEE.value,
        server_default=UserRole.EMPLOYEE.value,
    )
    # 预留停用能力：停用后无法登录，历史单据仍保留
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<User id={self.id} username={self.username!r} role={self.role!r}>"
