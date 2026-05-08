from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class LocationCode(BaseModel):
    """A named point/location used in the schedule."""
    code: str       # "П"
    name: str       # "Пассаж"
    sort_order: int = 0

    def to_dict(self) -> dict:
        return {"code": self.code, "name": self.name, "sort_order": self.sort_order}

    @classmethod
    def from_dict(cls, d: dict) -> "LocationCode":
        return cls(code=d["code"], name=d.get("name", d["code"]), sort_order=d.get("sort_order", 0))


class LocationPlan(BaseModel):
    """Monthly sales plan for a specific location."""
    location_code: str
    month_key: str       # "АПРЕЛЬ_2026"
    repair_plan: float = 0.0
    cosmetics_plan: float = 0.0
    shoes_plan: float = 0.0

    def to_dict(self) -> dict:
        return {
            "location_code": self.location_code,
            "month_key": self.month_key,
            "repair_plan": self.repair_plan,
            "cosmetics_plan": self.cosmetics_plan,
            "shoes_plan": self.shoes_plan,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LocationPlan":
        return cls(
            location_code=d["location_code"],
            month_key=d["month_key"],
            repair_plan=float(d.get("repair_plan", 0)),
            cosmetics_plan=float(d.get("cosmetics_plan", 0)),
            shoes_plan=float(d.get("shoes_plan", 0)),
        )


class LocationCodeCreate(BaseModel):
    code: str
    name: str
    sort_order: int = 0


class LocationCodeUpdate(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None


class LocationPlanUpsert(BaseModel):
    location_code: str
    month_key: str
    repair_plan: float = 0.0
    cosmetics_plan: float = 0.0
    shoes_plan: float = 0.0
