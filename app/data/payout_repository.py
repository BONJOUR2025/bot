from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.session import SessionLocal, init_db
from app.models.advance_request import AdvanceRequest
from app.utils.logger import log

# Status aliases from legacy JSON → canonical values
_STATUS_MAP = {
    "В ожидании": "Ожидает",
    "Ожидает одобрения": "Ожидает",
    "Ожидает выплаты": "Ожидает",
    "Разрешено": "Одобрено",
    "Утверждено": "Одобрено",
    "Подтверждено": "Одобрено",
    "Отказано": "Отклонено",
    "Проведено": "Выплачено",
    "Завершено": "Выплачено",
    "Выплачен": "Выплачено",
}


def normalize_status(status: str) -> str:
    return _STATUS_MAP.get(status, status)


def load_advance_requests(file_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Load all advance requests from the database (file_path ignored — kept for compat)."""
    repo = PayoutRepository()
    return repo.load_all()


class PayoutRepository:
    """Advance-request persistence backed by SQLite via SQLAlchemy."""

    def __init__(self, file_path: Optional[str] = None) -> None:
        # file_path kept for backward compatibility but not used
        init_db()
        log("📂 PayoutRepository initialised (SQLite)")

    def reload(self) -> None:
        """No-op: DB reads are always fresh."""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _session(self) -> Session:
        return SessionLocal()

    def _row_to_dict(self, row: AdvanceRequest) -> Dict[str, Any]:
        return row.to_dict()

    # ------------------------------------------------------------------
    # Public API (same contract as the old JSON-based repository)
    # ------------------------------------------------------------------

    def load_all(self) -> List[Dict[str, Any]]:
        with self._session() as db:
            rows = db.query(AdvanceRequest).order_by(AdvanceRequest.timestamp.desc()).all()
            return [self._row_to_dict(r) for r in rows]

    def list(
        self,
        employee_id: Optional[str] = None,
        payout_type: Optional[str] = None,
        status: Optional[str] = None,
        method: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self._session() as db:
            q = db.query(AdvanceRequest)
            if employee_id is not None:
                q = q.filter(AdvanceRequest.user_id == str(employee_id))
            if payout_type is not None:
                q = q.filter(AdvanceRequest.payout_type == payout_type)
            if status is not None:
                q = q.filter(AdvanceRequest.status == status)
            if method is not None:
                q = q.filter(AdvanceRequest.method == method)
            if from_date:
                q = q.filter(AdvanceRequest.timestamp >= from_date)
            if to_date:
                q = q.filter(AdvanceRequest.timestamp <= to_date + " 23:59:59")
            rows = q.order_by(AdvanceRequest.timestamp.desc()).all()
            return [self._row_to_dict(r) for r in rows]

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        with self._session() as db:
            row = AdvanceRequest(
                user_id=str(data.get("user_id", "")),
                name=data.get("name", ""),
                phone=data.get("phone", ""),
                card_number=data.get("card_number", ""),
                bank=data.get("bank", ""),
                amount=int(data.get("amount", 0)),
                method=data.get("method", ""),
                payout_type=data.get("payout_type"),
                status=normalize_status(data.get("status", "Ожидает")),
                timestamp=data.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                source_file=data.get("source_file"),
                note=data.get("note", ""),
                show_note_in_bot=bool(data.get("show_note_in_bot", False)),
                force_notify_cashier=bool(data.get("force_notify_cashier", False)),
                cash_move_id=data.get("cash_move_id") or None,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return self._row_to_dict(row)

    def update(self, payout_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        with self._session() as db:
            row = db.query(AdvanceRequest).filter(
                AdvanceRequest.id == int(payout_id)
            ).first()
            if row is None:
                return None
            for key, value in updates.items():
                if value is None:
                    continue
                if key == "status":
                    value = normalize_status(value)
                if hasattr(row, key):
                    setattr(row, key, value)
            db.commit()
            db.refresh(row)
            return self._row_to_dict(row)

    def delete(self, payout_id: str) -> bool:
        with self._session() as db:
            row = db.query(AdvanceRequest).filter(
                AdvanceRequest.id == int(payout_id)
            ).first()
            if row is None:
                return False
            db.delete(row)
            db.commit()
            return True

    def linked_cash_move_ids(self) -> set:
        """Return the set of all cash_move_id values that have a linked payout."""
        with self._session() as db:
            rows = db.query(AdvanceRequest.cash_move_id).filter(
                AdvanceRequest.cash_move_id.isnot(None)
            ).all()
            return {r[0] for r in rows}

    def delete_many(self, ids: List[str]) -> None:
        int_ids = []
        for i in ids:
            try:
                int_ids.append(int(i))
            except (TypeError, ValueError):
                pass
        if not int_ids:
            return
        with self._session() as db:
            db.query(AdvanceRequest).filter(AdvanceRequest.id.in_(int_ids)).delete(
                synchronize_session=False
            )
            db.commit()
