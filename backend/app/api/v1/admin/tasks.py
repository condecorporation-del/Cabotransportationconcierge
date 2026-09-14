import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import DbSession
from app.api.v1.admin.deps import CAN_EDIT, CurrentAdmin, require_csrf
from app.core.errors import AppError
from app.core.rate_limit import rate_limit
from app.models import AdminTask, AdminUser, TaskStatus
from app.schemas.tasks import AdminTaskIn, AdminTaskOut, AdminTaskPatch

router = APIRouter(
    prefix="/admin/tasks", tags=["admin-tasks"], dependencies=[Depends(rate_limit(60))]
)
NOT_FOUND = "Task not found."


async def _check_assignee(session: DbSession, assigned_to_admin_id: uuid.UUID | None) -> None:
    if assigned_to_admin_id is None:
        return
    exists = await session.scalar(select(AdminUser.id).where(AdminUser.id == assigned_to_admin_id))
    if exists is None:
        raise AppError("assignee_not_found", "That admin user does not exist.")


@router.get("")
async def list_tasks(
    _admin: CurrentAdmin,
    session: DbSession,
    status: Annotated[TaskStatus | None, Query()] = None,
    assigned_to_admin_id: uuid.UUID | None = None,
) -> list[AdminTaskOut]:
    query = select(AdminTask).order_by(AdminTask.due_date, AdminTask.due_time)
    if status is not None:
        query = query.where(AdminTask.status == status)
    if assigned_to_admin_id is not None:
        query = query.where(AdminTask.assigned_to_admin_id == assigned_to_admin_id)
    rows = (await session.scalars(query)).all()
    return [AdminTaskOut.model_validate(row) for row in rows]


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)])
async def create_task(
    body: AdminTaskIn, _admin: Annotated[AdminUser, Depends(CAN_EDIT)], session: DbSession
) -> AdminTaskOut:
    await _check_assignee(session, body.assigned_to_admin_id)
    task = AdminTask(**body.model_dump())
    session.add(task)
    await session.commit()
    return AdminTaskOut.model_validate(task)


async def admin_task(task_id: uuid.UUID, _admin: CurrentAdmin, session: DbSession) -> AdminTask:
    task = await session.get(AdminTask, task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return task


AdminTaskDep = Annotated[AdminTask, Depends(admin_task)]


@router.patch("/{task_id}", dependencies=[Depends(require_csrf)])
async def patch_task(
    task: AdminTaskDep,
    body: AdminTaskPatch,
    _admin: Annotated[AdminUser, Depends(CAN_EDIT)],
    session: DbSession,
) -> AdminTaskOut:
    changes = body.model_dump(exclude_unset=True)
    if "assigned_to_admin_id" in changes:
        await _check_assignee(session, changes["assigned_to_admin_id"])
    for key, value in changes.items():
        setattr(task, key, value)
    await session.commit()
    return AdminTaskOut.model_validate(task)


@router.delete(
    "/{task_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_csrf)]
)
async def delete_task(
    task: AdminTaskDep, _admin: Annotated[AdminUser, Depends(CAN_EDIT)], session: DbSession
) -> None:
    await session.delete(task)
    await session.commit()
