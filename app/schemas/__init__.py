"""Pydantic V2 Schema 统一出口。"""

from app.schemas.auth import LoginRequest, TokenOut
from app.schemas.common import ErrorBody, Message, Page, UTCDateTime
from app.schemas.dashboard import DashboardOut, TopPartOut
from app.schemas.inventory import InventoryLogOut
from app.schemas.order import OrderCreateBase, OrderItemIn, OrderItemOut, OrderOutBase
from app.schemas.part import PartCreate, PartOut, PartUpdate, PartWarningOut
from app.schemas.partner import PartnerCreate, PartnerOut
from app.schemas.purchase import PurchaseOrderCreate, PurchaseOrderOut
from app.schemas.sale import SaleOrderCreate, SaleOrderOut
from app.schemas.user import UserOut

__all__ = [
    "DashboardOut",
    "ErrorBody",
    "InventoryLogOut",
    "LoginRequest",
    "Message",
    "OrderCreateBase",
    "OrderItemIn",
    "OrderItemOut",
    "OrderOutBase",
    "Page",
    "PartCreate",
    "PartOut",
    "PartUpdate",
    "PartWarningOut",
    "PartnerCreate",
    "PartnerOut",
    "PurchaseOrderCreate",
    "PurchaseOrderOut",
    "SaleOrderCreate",
    "SaleOrderOut",
    "TokenOut",
    "TopPartOut",
    "UTCDateTime",
    "UserOut",
]
