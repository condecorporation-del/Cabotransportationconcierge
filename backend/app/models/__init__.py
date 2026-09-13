"""Registra todos los modelos en Base.metadata (lo necesita Alembic)."""

from app.models.admin import AdminRole, AdminSession, AdminUser
from app.models.catalog import (
    Activity,
    ActivityPackage,
    DiscountType,
    Extra,
    ExtraAutoRule,
    Hotel,
    PricingMode,
    Promotion,
    PromotionScope,
    Rate,
    ServiceScope,
    TripType,
    VehicleClass,
    Zone,
)
from app.models.company import Company, CompanySettings
from app.models.customer import Customer

__all__ = [
    "Activity",
    "ActivityPackage",
    "AdminRole",
    "AdminSession",
    "AdminUser",
    "Company",
    "CompanySettings",
    "Customer",
    "DiscountType",
    "Extra",
    "ExtraAutoRule",
    "Hotel",
    "PricingMode",
    "Promotion",
    "PromotionScope",
    "Rate",
    "ServiceScope",
    "TripType",
    "VehicleClass",
    "Zone",
]
