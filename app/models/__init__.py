"""ORM 模型统一出口：导入此包即可完成所有 Mapper 注册。"""

from app.models.audit_log import AuditLog
from app.models.customer import Customer, CustomerFollowup
from app.models.enums import ChangeType, OrderStatus, UserRole
from app.models.inventory_log import InventoryLog
from app.models.module import Module, UserModule
from app.models.part import Part
from app.models.purchase import PurchaseItem, PurchaseOrder
from app.models.sale import SaleItem, SaleOrder
from app.models.supplier import Supplier
from app.models.user import User

__all__ = [
    "AuditLog",
    "ChangeType",
    "Customer",
    "CustomerFollowup",
    "InventoryLog",
    "Module",
    "OrderStatus",
    "Part",
    "PurchaseItem",
    "PurchaseOrder",
    "SaleItem",
    "SaleOrder",
    "Supplier",
    "User",
    "UserModule",
    "UserRole",
]
