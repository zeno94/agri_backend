"""功能模块与用户模块授权。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Integer, PrimaryKeyConstraint, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, big_int_pk

if TYPE_CHECKING:
    from app.models.user import User


class Module(TimestampMixin, Base):
    __tablename__ = "modules"
    __table_args__ = (PrimaryKeyConstraint("id", name="pk_modules"),)

    id: Mapped[int] = mapped_column(big_int_pk(), primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    path: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    icon: Mapped[str] = mapped_column(String(50), nullable=False, default="Grid", server_default="Grid")
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("1"))
    is_admin_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("0"))

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Module id={self.id} code={self.code!r}>"


class UserModule(Base):
    __tablename__ = "user_modules"
    __table_args__ = (PrimaryKeyConstraint("user_id", "module_id", name="pk_user_modules"),)

    user_id: Mapped[int] = mapped_column(big_int_pk(), nullable=False, index=True)
    module_id: Mapped[int] = mapped_column(big_int_pk(), nullable=False, index=True)

    user: Mapped[User] = relationship(
        "User",
        primaryjoin="foreign(UserModule.user_id) == User.id",
        back_populates="module_links",
    )
    module: Mapped[Module] = relationship(
        "Module",
        primaryjoin="foreign(UserModule.module_id) == Module.id",
        lazy="joined",
    )
