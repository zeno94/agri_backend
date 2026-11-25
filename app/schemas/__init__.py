"""Pydantic V2 Schema 统一出口。"""

from app.schemas.audit import AuditLogOut
from app.schemas.auth import LoginRequest, TokenOut
from app.schemas.common import ErrorBody, Message, Page, UTCDateTime
from app.schemas.customer import (
    CustomerCreate,
    CustomerDetailOut,
    CustomerOptionOut,
    CustomerOut,
    CustomerStats,
    CustomerUpdate,
    FollowupCreate,
    FollowupOut,
)
from app.schemas.dashboard import DashboardOut, TopCustomerOut, TopPartOut, TopSupplierOut
from app.schemas.inventory import InventoryLogOut
from app.schemas.module import ModuleAdminOut, ModuleOut, ModuleUpdate
from app.schemas.order import OrderCreateBase, OrderItemIn, OrderItemOut, OrderOutBase
from app.schemas.part import PartCreate, PartOut, PartUpdate, PartWarningOut
from app.schemas.purchase import PurchaseOrderCreate, PurchaseOrderOut
from app.schemas.sale import SaleOrderCreate, SaleOrderOut
from app.schemas.supplier import (
    SupplierCreate,
    SupplierListItem,
    SupplierOptionOut,
    SupplierOut,
    SupplierUpdate,
)
from app.schemas.user import (
    PasswordReset,
    UserCreate,
    UserModulesUpdate,
    UserOut,
    UserUpdate,
)

__all__ = [
    "AuditLogOut",
    "CustomerCreate",
    "CustomerDetailOut",
    "CustomerOptionOut",
    "CustomerOut",
    "CustomerStats",
    "CustomerUpdate",
    "DashboardOut",
    "ErrorBody",
    "FollowupCreate",
    "FollowupOut",
    "InventoryLogOut",
    "LoginRequest",
    "Message",
    "ModuleAdminOut",
    "ModuleOut",
    "ModuleUpdate",
    "OrderCreateBase",
    "OrderItemIn",
    "OrderItemOut",
    "OrderOutBase",
    "Page",
    "PartCreate",
    "PartOut",
    "PartUpdate",
    "PartWarningOut",
    "PasswordReset",
    "PurchaseOrderCreate",
    "PurchaseOrderOut",
    "SaleOrderCreate",
    "SaleOrderOut",
    "SupplierCreate",
    "SupplierListItem",
    "SupplierOptionOut",
    "SupplierOut",
    "SupplierUpdate",
    "TokenOut",
    "TopCustomerOut",
    "TopPartOut",
    "TopSupplierOut",
    "UTCDateTime",
    "UserCreate",
    "UserModulesUpdate",
    "UserOut",
    "UserUpdate",
]
