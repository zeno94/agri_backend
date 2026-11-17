"""往来单位服务。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import partner as crud_partner
from app.models.partner import Partner
from app.schemas.common import Page
from app.schemas.partner import PartnerCreate, PartnerOut
from app.services.common import calc_pages


async def list_partners(
    db: AsyncSession,
    *,
    page: int,
    size: int,
    partner_type: str | None = None,
    name: str | None = None,
) -> Page[PartnerOut]:
    rows, total = await crud_partner.list_partners(
        db,
        page=page,
        size=size,
        partner_type=partner_type,
        name=name.strip() if name else None,
    )
    return Page[PartnerOut](
        items=[PartnerOut.model_validate(item) for item in rows],
        total=total,
        page=page,
        size=size,
        pages=calc_pages(total, size),
    )


async def create_partner(db: AsyncSession, payload: PartnerCreate) -> PartnerOut:
    partner: Partner = await crud_partner.create_partner(db, payload.model_dump())
    await db.commit()
    await db.refresh(partner)
    return PartnerOut.model_validate(partner)
