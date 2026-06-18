from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class VisitorEventIngest(BaseModel):
    salon_code: str
    direction: Literal["in", "out"]
    count: int = Field(default=1, ge=1, le=100)
    device_id: Optional[str] = None


class VisitorEvent(BaseModel):
    id: int
    salon_id: str
    direction: Literal["in", "out"]
    count: int
    device_id: Optional[str] = None
    created_at: str


class VisitorDailySummary(BaseModel):
    date: str
    salon_id: str
    salon_name: Optional[str] = None
    in_count: int
    out_count: int
    net: int
