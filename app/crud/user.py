"""用户数据访问。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import User


async def get_by_id(db: AsyncSession, user_id: int) -> User | None:
    return await db.scalar(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.modules))
        .execution_options(populate_existing=True)
    )


async def get_by_username(db: AsyncSession, username: str) -> User | None:
    return await db.scalar(
        select(User)
        .where(User.username == username)
        .options(selectinload(User.modules))
        .execution_options(populate_existing=True)
    )


async def list_users(db: AsyncSession) -> list[User]:
    rows = await db.scalars(select(User).options(selectinload(User.modules)).order_by(User.id.asc()))
    return list(rows.all())


async def create_user(db: AsyncSession, values: dict[str, Any]) -> User:
    user = User(**values)
    db.add(user)
    await db.flush()
    await db.refresh(user, attribute_names=["modules"])
    return user


async def update_user(db: AsyncSession, user: User, values: dict[str, Any]) -> User:
    for key, value in values.items():
        setattr(user, key, value)
    await db.flush()
    return user
