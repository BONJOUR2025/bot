"""Asset repository backed by SQLite (hr.db), shared safely between the
bot process and the API server process via WAL mode.

Replaces the previous JSON-file implementation which had an in-memory cache
that caused stale reads when the other process wrote to the file.
"""
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.db.session import engine
from app.utils.logger import log

_COLS = (
    "id", "employee_id", "employee_name", "position", "item_name", "size",
    "quantity", "issue_date", "return_date", "service_life",
    "notified_at", "acked_at", "created_at",
)


def _row(row) -> Dict[str, Any]:
    d = dict(row._mapping)
    # Normalise created_at to string if present
    if d.get("created_at") and not isinstance(d["created_at"], str):
        d["created_at"] = str(d["created_at"])
    return d


class AssetRepository:
    def list(self, employee_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with engine.connect() as conn:
            if employee_id:
                rows = conn.execute(
                    text("SELECT * FROM assets WHERE employee_id = :eid ORDER BY issue_date, id"),
                    {"eid": str(employee_id)},
                ).fetchall()
            else:
                rows = conn.execute(
                    text("SELECT * FROM assets ORDER BY issue_date, id")
                ).fetchall()
        return [_row(r) for r in rows]

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        params = {
            "employee_id":   str(data.get("employee_id", "")),
            "employee_name": data.get("employee_name") or "",
            "position":      data.get("position") or "",
            "item_name":     data.get("item_name") or "",
            "size":          data.get("size") or "",
            "quantity":      int(data.get("quantity") or 1),
            "issue_date":    data.get("issue_date") or "",
            "return_date":   data.get("return_date") or None,
            "service_life":  int(data["service_life"]) if data.get("service_life") else None,
            "notified_at":   data.get("notified_at") or None,
            "acked_at":      data.get("acked_at") or None,
        }
        with engine.begin() as conn:
            result = conn.execute(
                text("""
                    INSERT INTO assets
                        (employee_id, employee_name, position, item_name, size,
                         quantity, issue_date, return_date, service_life,
                         notified_at, acked_at)
                    VALUES
                        (:employee_id, :employee_name, :position, :item_name, :size,
                         :quantity, :issue_date, :return_date, :service_life,
                         :notified_at, :acked_at)
                """),
                params,
            )
            new_id = result.lastrowid
        return {**params, "id": new_id}

    def update(self, item_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        fields = {k: v for k, v in updates.items() if k != "id" and v is not None}
        if not fields:
            return self._get(item_id)
        set_clause = ", ".join(f"{k} = :{k}" for k in fields)
        with engine.begin() as conn:
            conn.execute(
                text(f"UPDATE assets SET {set_clause} WHERE id = :_id"),
                {**fields, "_id": int(item_id)},
            )
        return self._get(item_id)

    def delete(self, item_id: str) -> None:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM assets WHERE id = :id"),
                {"id": int(item_id)},
            )

    def _get(self, item_id: str) -> Optional[Dict[str, Any]]:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM assets WHERE id = :id"),
                {"id": int(item_id)},
            ).fetchone()
        return _row(row) if row else None

    def reassign_employee(self, old_employee_id: str, new_employee_id: str) -> int:
        with engine.begin() as conn:
            result = conn.execute(
                text("UPDATE assets SET employee_id = :new WHERE employee_id = :old"),
                {"new": str(new_employee_id), "old": str(old_employee_id)},
            )
        return result.rowcount
