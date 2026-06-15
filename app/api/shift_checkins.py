from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from app.api.dependencies import require_permission
from app.data.shift_checkin_repository import ShiftCheckinRepository
from app.schemas.shift_checkin import ShiftCheckin, ShiftCheckinManualCreate
from app.services.shift_checkin_service import ShiftCheckinService, get_shift_checkin_service
from app.services.work_hours import MOSCOW_TZ

MEDIA_DIR = Path(__file__).resolve().parent.parent.parent / "media_archive"


def create_shift_checkins_router(repo: ShiftCheckinRepository) -> APIRouter:
    router = APIRouter(prefix="/shift-checkins", tags=["ShiftCheckins"])

    @router.get("/", response_model=list[ShiftCheckin])
    async def list_shift_checkins(
        date_from: Optional[str] = Query(None),
        date_to: Optional[str] = Query(None),
        salon_id: Optional[str] = Query(None),
        employee_id: Optional[str] = Query(None),
        current=Depends(require_permission("shift-checkins")),
    ):
        return repo.list(
            date_from=date_from,
            date_to=date_to,
            salon_id=salon_id,
            employee_id=employee_id,
        )

    @router.post("/", response_model=ShiftCheckin)
    async def create_manual_shift_checkin(
        data: ShiftCheckinManualCreate,
        current=Depends(require_permission("shift-checkins")),
        service: ShiftCheckinService = Depends(get_shift_checkin_service),
    ):
        try:
            sent_at = datetime.strptime(f"{data.date} {data.time}", "%Y-%m-%d %H:%M")
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid_datetime")
        sent_at = sent_at.replace(tzinfo=MOSCOW_TZ)
        return await service.record_checkin(
            employee_id=data.employee_id,
            employee_name=data.employee_name,
            sent_at=sent_at,
            manual=True,
            added_by="admin",
        )

    @router.get("/{checkin_id}/photo")
    async def get_shift_checkin_photo(
        checkin_id: int,
        current=Depends(require_permission("shift-checkins")),
    ):
        record = repo.get(checkin_id)
        if not record or not record.get("photo_path"):
            raise HTTPException(status_code=404, detail="not_found")
        photo_path = (MEDIA_DIR / record["photo_path"]).resolve()
        if MEDIA_DIR not in photo_path.parents or not photo_path.is_file():
            raise HTTPException(status_code=404, detail="not_found")
        return FileResponse(photo_path)

    return router
