from pydantic import BaseModel
from typing import Optional


class SchedulePointOut(BaseModel):
    """Employee assignment for a single point."""

    point: str
    short: str
    employee: str
