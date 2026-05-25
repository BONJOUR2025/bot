from datetime import datetime
from typing import Dict, List, Optional

from app.db.session import SessionLocal
from app.models.payment_calendar import PaymentRecord, PaymentSchedule


class PaymentCalendarRepository:
    def _session(self):
        return SessionLocal()

    # ── Schedules ─────────────────────────────────────────────────────

    def list_schedules(self) -> List[Dict]:
        with self._session() as db:
            rows = db.query(PaymentSchedule).order_by(PaymentSchedule.day_of_month).all()
            return [r.to_dict() for r in rows]

    def get_schedule(self, schedule_id: int) -> Optional[Dict]:
        with self._session() as db:
            row = db.query(PaymentSchedule).filter(PaymentSchedule.id == schedule_id).first()
            return row.to_dict() if row else None

    def create_schedule(self, data: Dict) -> Dict:
        with self._session() as db:
            row = PaymentSchedule(**data)
            db.add(row)
            db.commit()
            db.refresh(row)
            return row.to_dict()

    def update_schedule(self, schedule_id: int, data: Dict) -> Optional[Dict]:
        with self._session() as db:
            row = db.query(PaymentSchedule).filter(PaymentSchedule.id == schedule_id).first()
            if not row:
                return None
            for k, v in data.items():
                setattr(row, k, v)
            db.commit()
            db.refresh(row)
            return row.to_dict()

    def delete_schedule(self, schedule_id: int) -> bool:
        with self._session() as db:
            row = db.query(PaymentSchedule).filter(PaymentSchedule.id == schedule_id).first()
            if not row:
                return False
            db.delete(row)
            db.commit()
            return True

    # ── Records ───────────────────────────────────────────────────────

    def get_or_create_records_for_month(self, year_month: str) -> List[Dict]:
        """Return records for a month; auto-create pending entries for active schedules."""
        with self._session() as db:
            schedules = db.query(PaymentSchedule).filter(PaymentSchedule.is_active == True).all()
            existing_ids = {
                r.schedule_id
                for r in db.query(PaymentRecord).filter(PaymentRecord.year_month == year_month).all()
            }
            for s in schedules:
                if s.id not in existing_ids:
                    db.add(PaymentRecord(schedule_id=s.id, year_month=year_month, status="pending"))
            db.commit()

            all_records = (
                db.query(PaymentRecord)
                .filter(PaymentRecord.year_month == year_month)
                .all()
            )
            result = []
            for r in all_records:
                d = r.to_dict()
                d["schedule"] = r.schedule.to_dict() if r.schedule else {}
                result.append(d)

        return sorted(result, key=lambda x: x.get("schedule", {}).get("day_of_month", 0))

    def update_record(self, record_id: int, data: Dict) -> Optional[Dict]:
        with self._session() as db:
            row = db.query(PaymentRecord).filter(PaymentRecord.id == record_id).first()
            if not row:
                return None
            for k, v in data.items():
                setattr(row, k, v)
            db.commit()
            db.refresh(row)
            d = row.to_dict()
            d["schedule"] = row.schedule.to_dict() if row.schedule else {}
            return d

    def get_active_schedules(self) -> List[Dict]:
        with self._session() as db:
            rows = db.query(PaymentSchedule).filter(PaymentSchedule.is_active == True).all()
            return [r.to_dict() for r in rows]


def get_payment_calendar_repository() -> PaymentCalendarRepository:
    return PaymentCalendarRepository()
