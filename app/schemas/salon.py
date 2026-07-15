from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field
import uuid
from datetime import datetime


class SalonContact(BaseModel):
    name: str = ""
    role: str = ""
    phone: str = ""
    email: str = ""


class SalonCreate(BaseModel):
    name: str
    code: str = ""
    # Separate from `code` (the letter-based schedule/shift point code) —
    # this is the 1-2 digit salon id that appears after the dash in Firebird
    # order numbers ("12345-6"), used to attribute KPI commission per salon.
    order_code: str = ""
    # Agbis SCLADS.ID values ("Склад приёма" = DOCS_ORDER.SCLAD_KREDIT_ID)
    # bound to this salon — fallback attribution for orders whose doc_num
    # has no matching order_code (e.g. corporate/internal-department sales
    # routed through a salon's physical warehouse). A salon can have more
    # than one (e.g. a чистомат sub-point sharing the same location).
    sclad_ids: list[int] = Field(default_factory=list)
    address: str = ""
    phone: str = ""
    status: str = "active"          # active | renovation | closed

    point_type: str = "ТЦ"         # ТЦ | Улица | Рынок | Другое
    area_sqm: Optional[float] = None
    opening_date: Optional[str] = None  # ISO date YYYY-MM-DD

    work_hours_weekday: str = ""
    work_hours_weekend: str = ""

    legal_entity: str = ""

    employees: list[str] = Field(default_factory=list)   # employee codes

    # Shopping-center / landlord contacts
    tc_name: str = ""
    tc_contacts: list[SalonContact] = Field(default_factory=list)

    # Rent
    rent_rate: Optional[float] = None
    rent_payment_day: Optional[int] = None
    rent_notes: str = ""

    notes: str = ""


class SalonUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    order_code: Optional[str] = None
    sclad_ids: Optional[list[int]] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    status: Optional[str] = None
    point_type: Optional[str] = None
    area_sqm: Optional[float] = None
    opening_date: Optional[str] = None
    work_hours_weekday: Optional[str] = None
    work_hours_weekend: Optional[str] = None
    legal_entity: Optional[str] = None
    employees: Optional[list[str]] = None
    tc_name: Optional[str] = None
    tc_contacts: Optional[list[SalonContact]] = None
    rent_rate: Optional[float] = None
    rent_payment_day: Optional[int] = None
    rent_notes: Optional[str] = None
    notes: Optional[str] = None


class Salon(SalonCreate):
    id: str
    created_at: str
    updated_at: str

    @classmethod
    def from_dict(cls, data: dict) -> "Salon":
        tc_contacts_raw = data.get("tc_contacts") or []
        tc_contacts = [
            SalonContact(**c) if isinstance(c, dict) else c
            for c in tc_contacts_raw
        ]
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            code=data.get("code", ""),
            order_code=data.get("order_code", ""),
            sclad_ids=[int(x) for x in (data.get("sclad_ids") or [])],
            address=data.get("address", ""),
            phone=data.get("phone", ""),
            status=data.get("status", "active"),
            point_type=data.get("point_type", "ТЦ"),
            area_sqm=data.get("area_sqm"),
            opening_date=data.get("opening_date"),
            work_hours_weekday=data.get("work_hours_weekday", ""),
            work_hours_weekend=data.get("work_hours_weekend", ""),
            legal_entity=data.get("legal_entity", ""),
            employees=data.get("employees") or [],
            tc_name=data.get("tc_name", ""),
            tc_contacts=tc_contacts,
            rent_rate=data.get("rent_rate"),
            rent_payment_day=data.get("rent_payment_day"),
            rent_notes=data.get("rent_notes", ""),
            notes=data.get("notes", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "code": self.code,
            "order_code": self.order_code,
            "sclad_ids": self.sclad_ids,
            "address": self.address,
            "phone": self.phone,
            "status": self.status,
            "point_type": self.point_type,
            "area_sqm": self.area_sqm,
            "opening_date": self.opening_date,
            "work_hours_weekday": self.work_hours_weekday,
            "work_hours_weekend": self.work_hours_weekend,
            "legal_entity": self.legal_entity,
            "employees": self.employees,
            "tc_name": self.tc_name,
            "tc_contacts": [c.dict() for c in self.tc_contacts],
            "rent_rate": self.rent_rate,
            "rent_payment_day": self.rent_payment_day,
            "rent_notes": self.rent_notes,
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def new_salon(data: SalonCreate) -> Salon:
    now = datetime.utcnow().isoformat()
    return Salon(
        id=str(uuid.uuid4()),
        created_at=now,
        updated_at=now,
        **data.dict(),
    )
