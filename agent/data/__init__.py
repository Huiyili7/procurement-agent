"""数据层：通过 PurchaseRepository 接口隔离数据来源(seed/real)。"""
from .models import PurchaseRecord
from .repository import PurchaseRepository, get_repository

__all__ = ["PurchaseRecord", "PurchaseRepository", "get_repository"]
