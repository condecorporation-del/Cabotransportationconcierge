"""Registra todos los modelos en Base.metadata (lo necesita Alembic)."""

from app.models.admin import AdminRole, AdminSession, AdminUser
from app.models.company import Company, CompanySettings

__all__ = ["AdminRole", "AdminSession", "AdminUser", "Company", "CompanySettings"]
