import io
import json
import os
import sys
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .dependencies import require_permission
from app.settings import settings
from app.utils.logger import LOGS_DIR

# JSON files that can be cleaned up by archiving old records.
# Each entry: (filename, date_field_name)
# NOTE: advance_requests are now stored in SQLite (hr.db) — no longer archived here.
ARCHIVABLE = [
    ("bonuses_penalties.json", "date"),
    ("adjustments.json", "date"),
    ("messages.json", "timestamp"),
]


def _read_date(record: dict, field: str) -> Optional[date]:
    raw = record.get(field)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw)[:10]).date()
    except Exception:
        return None


def _get_payroll_excel_path() -> Path:
    try:
        data = json.loads(Path("config.json").read_text(encoding="utf-8"))
        if p := data.get("PAYROLL_EXCEL_FILE"):
            return Path(p)
    except Exception:
        pass
    return Path(settings.payroll_excel_file)


class ArchiveRequest(BaseModel):
    before: str  # YYYY-MM-DD


def create_system_router() -> APIRouter:
    router = APIRouter(prefix="/system", tags=["system"])
    perm = require_permission("settings")

    @router.get("/browse")
    async def browse_files(
        path: str = Query(""),
        ext: str = Query(""),
        _=Depends(perm),
    ):
        """List directory contents for the file picker."""
        exts = {e.strip().lower() for e in ext.split(",") if e.strip()} if ext else set()

        # Root level: list drives on Windows, "/" on Linux
        if not path:
            if sys.platform == "win32":
                import string
                drives = [
                    {"name": f"{d}:\\", "full_path": f"{d}:\\", "is_dir": True}
                    for d in string.ascii_uppercase
                    if os.path.exists(f"{d}:\\")
                ]
                return {"path": "", "parent": None, "items": drives}
            else:
                path = "/"

        p = Path(path)
        if not p.exists():
            raise HTTPException(status_code=404, detail="Путь не найден")
        if not p.is_dir():
            raise HTTPException(status_code=400, detail="Не директория")

        try:
            entries = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        except PermissionError:
            raise HTTPException(status_code=403, detail="Нет доступа")

        items = []
        for entry in entries:
            try:
                is_dir = entry.is_dir()
                if not is_dir and exts and entry.suffix.lower() not in exts:
                    continue
                items.append({"name": entry.name, "full_path": str(entry), "is_dir": is_dir})
            except OSError:
                pass

        parent = str(p.parent) if str(p.parent) != str(p) else None
        # On Windows when at drive root (e.g. C:\), parent → drives list
        if sys.platform == "win32" and parent and Path(parent) == p:
            parent = ""
        return {"path": str(p), "parent": parent, "items": items}

    @router.get("/logs")
    async def list_logs(_=Depends(perm)):
        """Log files under logs/, grouped by their top-level subdirectory
        (bot, users, payouts, messages, leave_requests, payment_calendar —
        see app/utils/logger.py for what writes into each). A stray file
        directly under logs/ (leftover from before this layout, or a future
        addition that doesn't use a subfolder) is grouped under "—"."""
        folders: dict[str, list[dict]] = {}
        if LOGS_DIR.exists():
            for p in sorted(LOGS_DIR.rglob("*.log*")):
                if not p.is_file():
                    continue
                rel = p.relative_to(LOGS_DIR)
                parts = rel.parts
                folder = parts[0] if len(parts) > 1 else "—"
                stat = p.stat()
                folders.setdefault(folder, []).append({
                    "name": rel.as_posix(),
                    "file": parts[-1],
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
        result = [
            {
                "name": folder,
                "files": files,
                "count": len(files),
                "total_size": sum(f["size"] for f in files),
            }
            for folder, files in sorted(folders.items())
        ]
        return {"folders": result}

    @router.get("/logs/content")
    async def log_content(
        name: str = Query(...),
        lines: int = Query(500, ge=1, le=5000),
        _=Depends(perm),
    ):
        """Return the last N lines of a log file."""
        base = LOGS_DIR.resolve()
        path = (base / name).resolve()
        if base not in path.parents and path != base:
            raise HTTPException(status_code=400, detail="invalid_path")
        if not path.is_file():
            raise HTTPException(status_code=404, detail="not_found")

        with path.open("r", encoding="utf-8", errors="replace") as f:
            content_lines = f.readlines()
        tail = content_lines[-lines:]
        return {
            "name": name,
            "lines": len(content_lines),
            "content": "".join(reversed(tail)),
        }

    @router.get("/status")
    async def system_status(_=Depends(perm)):
        result: dict = {}

        # Firebird
        try:
            from app.services.firebird_service import FIREBIRD_AVAILABLE, _connect
            if not FIREBIRD_AVAILABLE:
                result["firebird"] = {"ok": False, "error": "Библиотека fdb не установлена"}
            else:
                conn = _connect()
                conn.close()
                result["firebird"] = {"ok": True}
        except Exception as e:
            result["firebird"] = {"ok": False, "error": str(e)}

        # Payroll Excel file
        path = _get_payroll_excel_path()
        if path.exists():
            result["payroll_excel"] = {"ok": True, "path": str(path)}
        else:
            result["payroll_excel"] = {
                "ok": False,
                "path": str(path),
                "error": f"Файл не найден: {path}",
            }

        return result

    @router.get("/backup")
    async def download_backup(_=Depends(perm)):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in Path(".").glob("*.json"):
                try:
                    zf.write(p, p.name)
                except Exception:
                    pass
            db_path = Path("hr.db")
            if db_path.exists():
                try:
                    zf.write(db_path, db_path.name)
                except Exception:
                    pass
        buf.seek(0)
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="backup_{ts}.zip"'},
        )

    @router.post("/archive")
    async def archive_old_records(body: ArchiveRequest, _=Depends(perm)):
        try:
            cutoff = datetime.fromisoformat(body.before).date()
        except ValueError:
            return {"error": "Неверный формат даты, ожидается YYYY-MM-DD"}

        report = {}
        ts = body.before.replace("-", "")

        for filename, date_field in ARCHIVABLE:
            p = Path(filename)
            if not p.exists():
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, list):
                continue

            old_recs = [r for r in data if (d := _read_date(r, date_field)) and d < cutoff]
            new_recs = [r for r in data if (d := _read_date(r, date_field)) is None or d >= cutoff]

            if not old_recs:
                report[filename] = {"archived": 0, "kept": len(new_recs)}
                continue

            # Save old records to archive file
            stem = p.stem
            archive_path = Path(f"{stem}_archive_{ts}.json")
            # Merge with existing archive if present
            existing: list = []
            if archive_path.exists():
                try:
                    existing = json.loads(archive_path.read_text(encoding="utf-8"))
                except Exception:
                    existing = []
            archive_path.write_text(
                json.dumps(existing + old_recs, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            p.write_text(
                json.dumps(new_recs, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            report[filename] = {
                "archived": len(old_recs),
                "kept": len(new_recs),
                "archive_file": str(archive_path),
            }

        return {"ok": True, "cutoff": body.before, "files": report}

    return router
