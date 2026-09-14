"""Tareas compartidas del equipo (WORKPLAN F6.9)."""

import uuid
from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, Field

from app.models import TaskCategory, TaskStatus
from app.schemas.quotes import _Strict


class AdminTaskIn(_Strict):
    title: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    due_date: date | None = None
    due_time: time | None = None
    category: TaskCategory = TaskCategory.OTHER
    assigned_to_admin_id: uuid.UUID | None = None


class AdminTaskPatch(_Strict):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    due_date: date | None = None
    due_time: time | None = None
    category: TaskCategory | None = None
    status: TaskStatus | None = None
    assigned_to_admin_id: uuid.UUID | None = None


class AdminTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    due_date: date | None
    due_time: time | None
    category: TaskCategory
    status: TaskStatus
    assigned_to_admin_id: uuid.UUID | None
    created_at: datetime
