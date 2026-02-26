from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TaskCategory(BaseModel):
    id: Optional[int] = None
    name: str
    color: str = '#6366f1'
    icon: str = '📋'
    created_at: Optional[datetime] = None


class TaskCategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    color: str = '#6366f1'
    icon: str = '📋'


class TaskCategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    color: Optional[str] = None
    icon: Optional[str] = None
