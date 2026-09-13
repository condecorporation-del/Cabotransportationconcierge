"""Registra todos los modelos en Base.metadata (lo necesita Alembic)."""

from app.models.admin import AdminRole, AdminSession, AdminUser
from app.models.booking import (
    Booking,
    BookingItem,
    BookingLeg,
    BookingSource,
    BookingStatus,
    BookingType,
    ItemType,
    LegStatus,
    LegType,
)
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
    "Booking",
    "BookingItem",
    "BookingLeg",
    "BookingSource",
    "BookingStatus",
    "BookingType",
    "Company",
    "CompanySettings",
    "Customer",
    "DiscountType",
    "Extra",
    "ExtraAutoRule",
    "Hotel",
    "ItemType",
    "LegStatus",
    "LegType",
    "PricingMode",
    "Promotion",
    "PromotionScope",
    "Rate",
    "ServiceScope",
    "TripType",
    "VehicleClass",
    "Zone",
]
