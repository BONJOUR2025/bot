from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, List

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.types import Employee, EmployeeStatus
from app.db.base_class import Base
from app.db.session import SessionLocal, engine, session_scope
from app.models.employee import Employee as EmployeeModel
from app.settings import settings
from app.utils.logger import log
from .json_storage import JsonStorage


class EmployeeRepository:
    """Репозиторий сотрудников с хранением в SQL."""

    def __init__(self, storage: JsonStorage | None = None, session: Session | None = None) -> None:
        self._storage = storage or JsonStorage(settings.users_file)
        self._external_session = session
        Base.metadata.create_all(bind=engine)
        self._seed_from_json()

    def _get_session(self) -> Session:
        return self._external_session or SessionLocal()

    def _close_session(self, session: Session) -> None:
        if self._external_session is None:
            session.close()

    def _seed_from_json(self) -> None:
        """Заполняет таблицу из JSON, если она пуста."""

        with session_scope() as session:
            existing = session.scalar(select(func.count(EmployeeModel.id)))
            if existing:
                return
            payload = self._storage.load() or {}
            if not payload:
                return
            log("⚙️  Первичная инициализация сотрудников из JSON")
            for uid, raw in payload.items():
                try:
                    employee = self._create_employee(uid, raw)
                    session.merge(self._model_from_entity(employee))
                except Exception as exc:  # pragma: no cover - защитный лог
                    log(f"⚠️ Не удалось загрузить сотрудника {uid}: {exc}")

    @staticmethod
    def _parse_date(value) -> date | None:
        if not value:
            return None
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value))
        except Exception:
            return None

    @staticmethod
    def _parse_datetime(value) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value))
        except Exception:
            return None

    def _create_employee(self, uid: str, data: dict) -> Employee:
        record = {
            "id": str(uid),
            "name": data.get("name", ""),
            "full_name": data.get("full_name", ""),
            "phone": data.get("phone", ""),
            "position": data.get("position", ""),
            "is_admin": data.get("is_admin", False),
            "card_number": data.get("card_number", ""),
            "bank": data.get("bank", ""),
            "work_place": data.get("work_place", ""),
            "clothing_size": data.get("clothing_size", ""),
            "birthdate": self._parse_date(data.get("birthdate")),
            "note": data.get("note", ""),
            "photo_url": data.get("photo_url", ""),
            "status": EmployeeStatus(data.get("status", "active")),
            "created_at": self._parse_datetime(data.get("created_at")) or datetime.utcnow(),
            "tags": data.get("tags", []) or [],
            "payout_chat_key": data.get("payout_chat_key"),
            "archived": bool(data.get("archived", False)),
            "archived_at": self._parse_datetime(data.get("archived_at")),
        }
        return Employee(**record)

    @staticmethod
    def _model_from_entity(employee: Employee) -> EmployeeModel:
        return EmployeeModel(
            id=str(employee.id),
            name=employee.name,
            full_name=employee.full_name,
            phone=employee.phone,
            position=employee.position,
            is_admin=employee.is_admin,
            card_number=employee.card_number,
            bank=employee.bank,
            work_place=employee.work_place,
            clothing_size=employee.clothing_size,
            birthdate=employee.birthdate,
            note=employee.note,
            photo_url=employee.photo_url,
            status=employee.status.value,
            created_at=employee.created_at,
            tags=employee.tags,
            payout_chat_key=employee.payout_chat_key,
            archived=employee.archived,
            archived_at=employee.archived_at,
        )

    @staticmethod
    def _entity_from_model(model: EmployeeModel) -> Employee:
        return Employee(
            id=str(model.id),
            name=model.name,
            full_name=model.full_name or "",
            phone=model.phone or "",
            position=model.position or "",
            is_admin=bool(model.is_admin),
            card_number=model.card_number or "",
            bank=model.bank or "",
            work_place=model.work_place or "",
            clothing_size=model.clothing_size or "",
            birthdate=model.birthdate,
            note=model.note or "",
            photo_url=model.photo_url or "",
            status=EmployeeStatus(model.status or "active"),
            created_at=model.created_at or datetime.utcnow(),
            tags=list(model.tags or []),
            payout_chat_key=model.payout_chat_key,
            archived=bool(model.archived),
            archived_at=model.archived_at,
        )

    def list_employees(self, **filters) -> List[Employee]:
        archived_filter = filters.get("archived") if "archived" in filters else False
        session = self._get_session()
        try:
            stmt = select(EmployeeModel)
            if archived_filter is not None:
                stmt = stmt.where(EmployeeModel.archived == archived_filter)
            status = filters.get("status")
            if status:
                statuses: Iterable[str] = status if isinstance(status, list) else [status]
                stmt = stmt.where(EmployeeModel.status.in_(list(statuses)))
            position = filters.get("position")
            if position:
                positions: Iterable[str] = position if isinstance(position, list) else [position]
                stmt = stmt.where(EmployeeModel.position.in_(list(positions)))
            employees = session.scalars(stmt).all()
            birthday_today = filters.get("birthday_today")
            tags_filter = set(filters.get("tags") or [])
            result: list[Employee] = []
            today_mmdd = datetime.utcnow().date().timetuple()[1:3]
            for model in employees:
                entity = self._entity_from_model(model)
                if birthday_today:
                    if not entity.birthdate or entity.birthdate.timetuple()[1:3] != today_mmdd:
                        continue
                if tags_filter and not tags_filter.intersection(set(entity.tags)):
                    continue
                result.append(entity)
            return result
        finally:
            self._close_session(session)

    def get_employee(self, employee_id: str) -> Employee | None:
        session = self._get_session()
        try:
            model = session.get(EmployeeModel, str(employee_id))
            return self._entity_from_model(model) if model else None
        finally:
            self._close_session(session)

    def add_employee(self, employee: Employee) -> None:
        session = self._get_session()
        try:
            session.add(self._model_from_entity(employee))
            session.commit()
        finally:
            self._close_session(session)

    def update_employee(self, employee: Employee) -> None:
        session = self._get_session()
        try:
            db_emp = session.get(EmployeeModel, str(employee.id))
            if not db_emp:
                return
            for key, value in self._model_from_entity(employee).__dict__.items():
                if key.startswith("_"):
                    continue
                setattr(db_emp, key, value)
            session.commit()
        finally:
            self._close_session(session)

    def delete_employee_by_id(self, employee_id: str) -> None:
        session = self._get_session()
        try:
            db_emp = session.get(EmployeeModel, str(employee_id))
            if db_emp:
                session.delete(db_emp)
                session.commit()
        finally:
            self._close_session(session)

    def save_employees(self, employees: List[Employee]) -> None:
        session = self._get_session()
        try:
            session.query(EmployeeModel).delete()
            session.add_all([self._model_from_entity(e) for e in employees])
            session.commit()
        finally:
            self._close_session(session)
