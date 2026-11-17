"""ORM 模型统一出口：导入此包即可完成所有 Mapper 注册。"""

from app.models.enums import ChangeType, OrderStatus, PartnerType, UserRole
from app.models.inventory_log import InventoryLog
from app.models.part import Part
from app.models.partner import Partner
from app.models.purchase import PurchaseItem, PurchaseOrder
from app.models.sale import SaleItem, SaleOrder
from app.models.user import User

__all__ = [
    "ChangeType",
    "InventoryLog",
    "OrderStatus",
    "Partner",
    "PartnerType",
    "Part",
    "PurchaseItem",
    "PurchaseOrder",
    "SaleItem",
    "SaleOrder",
    "User",
    "UserRole",
]
