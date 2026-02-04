from typing import List, Optional

from app.schemas.vacation import Vacation, VacationCreate, VacationUpdate
from app.data.vacation_repository import VacationRepository


class VacationService:
    def __init__(self, repo: Optional[VacationRepository] = None) -> None:
        self._repo = repo or VacationRepository()

    async def list_vacations(
        self,
        employee_id: Optional[str] = None,
        vac_type: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[Vacation]:
        rows = self._repo.list(employee_id, vac_type, date_from, date_to)
        return [Vacation(**r) for r in rows]

    async def create_vacation(self, data: VacationCreate) -> Vacation:
        self._validate_dates(data.start_date, data.end_date)
        created = self._repo.create(data.model_dump())
        return Vacation(**created)

    async def update_vacation(
            self,
            vac_id: str,
            data: VacationUpdate) -> Optional[Vacation]:
        existing = next(
            (v for v in self._repo.list() if str(v.get("id")) == str(vac_id)),
            None,
        )
        if not existing:
            return None
        start = data.start_date or existing.get("start_date")
        end = data.end_date or existing.get("end_date")
        self._validate_dates(start, end)
        updated = self._repo.update(vac_id, data.model_dump(exclude_none=True))
        return Vacation(**updated) if updated else None

    async def delete_vacation(self, vac_id: str) -> None:
        self._repo.delete(vac_id)

    async def list_active(self) -> List[Vacation]:
        rows = self._repo.list_active()
        return [Vacation(**r) for r in rows]

    async def list_tomorrow(self) -> List[Vacation]:
        rows = self._repo.list_tomorrow()
        return [Vacation(**r) for r in rows]

    def get_vacation_employee(self, vac_id: str) -> Optional[str]:
        for item in self._repo.list():
            if str(item.get("id")) == str(vac_id):
                employee_id = item.get("employee_id")
                return str(employee_id) if employee_id is not None else None
        return None

    @staticmethod
    def _validate_dates(start: str, end: str) -> None:
        if start and end and start > end:
            raise ValueError("start_date must be before end_date")
