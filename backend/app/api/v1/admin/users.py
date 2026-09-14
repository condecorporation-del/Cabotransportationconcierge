import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import DbSession
from app.api.v1.admin.deps import OWNER_ONLY, CurrentAdmin, require_csrf
from app.core.errors import AppError
from app.core.rate_limit import rate_limit
from app.core.security import hash_password
from app.models import AdminUser, AuditActor, AuditLog
from app.schemas.users import AdminUserIn, AdminUserOut, AdminUserPatch, AuditLogOut, AuditLogPage

router = APIRouter(tags=["admin-users"], dependencies=[Depends(rate_limit(60))])
NOT_FOUND = "Admin user not found."
MAX_PAGE_SIZE = 100


@router.get("/admin/users")
async def list_users(
    _admin: Annotated[AdminUser, Depends(OWNER_ONLY)], session: DbSession
) -> list[AdminUserOut]:
    rows = (await session.scalars(select(AdminUser).order_by(AdminUser.email))).all()
    return [AdminUserOut.model_validate(row) for row in rows]


@router.post(
    "/admin/users", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)]
)
async def create_user(
    body: AdminUserIn,
    _admin: Annotated[AdminUser, Depends(OWNER_ONLY)],
    session: DbSession,
) -> AdminUserOut:
    email = body.email.strip().lower()
    exists = await session.scalar(select(AdminUser.id).where(func.lower(AdminUser.email) == email))
    if exists is not None:
        raise AppError("email_taken", "An admin with that email already exists.")
    user = AdminUser(email=email, password_hash=hash_password(body.password), role=body.role)
    session.add(user)
    await session.commit()
    return AdminUserOut.model_validate(user)


@router.patch("/admin/users/{user_id}", dependencies=[Depends(require_csrf)])
async def patch_user(
    user_id: uuid.UUID,
    body: AdminUserPatch,
    admin: Annotated[AdminUser, Depends(OWNER_ONLY)],
    session: DbSession,
) -> AdminUserOut:
    """Solo `role` e `is_active`: nunca la contraseña ni el TOTP por esta ruta (F6.13)."""
    user = await session.get(AdminUser, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    changes = body.model_dump(exclude_unset=True)
    before = {key: getattr(user, key) for key in changes}
    for key, value in changes.items():
        setattr(user, key, value)
    if changes:
        session.add(
            AuditLog(
                actor=AuditActor.ADMIN,
                admin_user_id=admin.id,
                action="update",
                entity="admin_users",
                entity_id=user.id,
                before={k: getattr(v, "value", v) for k, v in before.items()},
                after={k: getattr(v, "value", v) for k, v in changes.items()},
            )
        )
    await session.commit()
    return AdminUserOut.model_validate(user)


@router.get("/admin/audit-logs")
async def list_audit_logs(
    _admin: CurrentAdmin,
    session: DbSession,
    entity: Annotated[str | None, Query(max_length=40)] = None,
    entity_id: uuid.UUID | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
) -> AuditLogPage:
    query = select(AuditLog)
    if entity is not None:
        query = query.where(AuditLog.entity == entity)
    if entity_id is not None:
        query = query.where(AuditLog.entity_id == entity_id)

    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = await session.scalars(
        query.order_by(AuditLog.created_at.desc()).limit(page_size).offset((page - 1) * page_size)
    )
    return AuditLogPage(
        items=[AuditLogOut.model_validate(row) for row in rows],
        total=total or 0,
        page=page,
        page_size=page_size,
    )
