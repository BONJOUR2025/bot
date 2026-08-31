from datetime import datetime, date, time
from typing import Optional, List

from pydantic import BaseModel, Field


class Task(BaseModel):
    """Task response model."""
    id: Optional[int] = None
    title: str
    description: Optional[str] = None
    due_date: Optional[date] = None
    due_time: Optional[time] = None
    priority: str = "medium"  # low, medium, high, urgent
    status: str = "todo"  # todo, in_progress, done
    category: Optional[str] = None
    tags: List[str] = []
    reminder_minutes: Optional[int] = None  # minutes before due_date/time
    reminder_sent: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_by: Optional[str] = None  # user who created
    # Кандидат, к которому привязана задача (режим «Прозвон»). Обычная задача
    # его не имеет — связь появляется только у звонков, назначенных на
    # конкретного человека, и позволяет перенос задачи двигать расписание
    # звонка. Хранилище задач — schemaless JSON, миграция не нужна.
    candidate_id: Optional[int] = None


class TaskCreate(BaseModel):
    """Schema for creating a task."""
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = Field(None, max_length=5000)
    due_date: Optional[date] = None
    due_time: Optional[time] = None
    priority: str = "medium"
    status: str = "todo"
    category: Optional[str] = None
    tags: List[str] = []
    reminder_minutes: Optional[int] = None
    candidate_id: Optional[int] = None


class TaskUpdate(BaseModel):
    """Schema for updating a task."""
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = Field(None, max_length=5000)
    due_date: Optional[date] = None
    due_time: Optional[time] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    reminder_minutes: Optional[int] = None
    reminder_sent: Optional[bool] = None
    candidate_id: Optional[int] = None


class TaskStats(BaseModel):
    """Task statistics for dashboard."""
    total: int = 0
    todo: int = 0
    in_progress: int = 0
    done: int = 0
    overdue: int = 0
    due_today: int = 0
    due_this_week: int = 0


TASK_PRIORITIES = ["low", "medium", "high", "urgent"]
TASK_STATUSES = ["todo", "in_progress", "done"]
