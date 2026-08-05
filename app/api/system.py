import asyncio
import io
import json
import os
import subprocess
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
from app.utils.logger import LOGS_DIR, PROCESSES_LOG_DIR

# A process writes its heartbeat every 60s (see write_heartbeat callers in
# app/main.py, app/vk_main.py, app/api/__init__.py) — 3x that is generous
# slack for a slow tick without flapping the status between checks.
HEARTBEAT_STALE_AFTER_S = 180
PROCESS_LABELS = {
    "telegram_bot": "Telegram-бот",
    "vk_bot": "VK-бот",
    "api_server": "Веб-сервер / админка",
    "xtunnel": "Туннель (xtunnel)",
    "fdb_warmer": "Прогрев кэша Agbis",
}
# Heartbeat name -> pm2 process name (see deploy.ps1 for the pm2 fleet).
PROCESS_TO_PM2 = {
    "telegram_bot": "bot-main",
    "vk_bot": "bot-vk",
    "api_server": "bot-app",
    "xtunnel": "xtunnel",
    "fdb_warmer": "bot-warmer",
}
# xtunnel is a compiled binary, not one of our own processes — there's no
# write_heartbeat() call we can add to it, so its status/restart-detection
# comes from pm2's own view (pid/uptime/status) instead of a heartbeat file.
PM2_STATUS_PROCESSES = {"xtunnel"}
REPO_ROOT = Path(__file__).resolve().parents[2]


def _launch_restart_watcher(pm2_name: str, heartbeat_name: str, label: str, mode: str) -> None:
    """Spawn app/utils/restart_watcher.py as a fully detached process.
    Must be detached (not an asyncio task in this process) since
    restarting "api_server" restarts the very process handling this
    request — an in-process task would die with it before it could notify
    anyone."""
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    log_path = PROCESSES_LOG_DIR / "restart_watcher.log"
    with open(log_path, "a", encoding="utf-8") as logf:
        subprocess.Popen(
            [sys.executable, "-m", "app.utils.restart_watcher", pm2_name, heartbeat_name, label, mode],
            cwd=str(REPO_ROOT),
            stdin=subprocess.DEVNULL,
            stdout=logf,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
            close_fds=True,
        )


def _pm2_process_status(name: str) -> dict:
    """Status for a pm2-managed process with no heartbeat file (xtunnel) —
    read straight from `pm2 jlist` instead."""
    label = PROCESS_LABELS.get(name, name)
    pm2_name = PROCESS_TO_PM2.get(name, name)
    proc = None
    try:
        result = subprocess.run(
            ["pm2", "jlist"], shell=True, capture_output=True,
            encoding="utf-8", errors="replace", timeout=15,
        )
        procs = json.loads(result.stdout)
        proc = next((p for p in procs if p.get("name") == pm2_name), None)
    except Exception:
        proc = None

    if proc is None:
        return {
            "name": name, "label": label, "online": False, "kind": "pm2",
            "last_seen": None, "age_s": None, "pid": None,
            "cpu_pct": None, "memory_mb": None,
        }

    env = proc.get("pm2_env") or {}
    online = env.get("status") == "online"
    last_seen, age_s = None, None
    pm_uptime_ms = env.get("pm_uptime")
    if pm_uptime_ms:
        started_at = datetime.fromtimestamp(pm_uptime_ms / 1000)
        last_seen = started_at.isoformat(timespec="seconds")
        age_s = (datetime.now() - started_at).total_seconds()
    monit = proc.get("monit") or {}
    memory = monit.get("memory")
    return {
        "name": name, "label": label, "online": online, "kind": "pm2",
        "last_seen": last_seen, "age_s": age_s, "pid": proc.get("pid"),
        "cpu_pct": monit.get("cpu"),
        "memory_mb": round(memory / (1024 * 1024), 1) if memory else None,
    }

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

    @router.get("/process-status")
    async def process_status(_=Depends(perm)):
        """Latest heartbeat per long-running process (bot(s), API server) —
        online/offline computed from how stale each heartbeat is, not just
        whether the process crashed (a hung-but-alive process stops
        heartbeating too)."""
        now = datetime.now()
        items = []
        seen = set(PM2_STATUS_PROCESSES)
        if PROCESSES_LOG_DIR.exists():
            for p in sorted(PROCESSES_LOG_DIR.glob("*.status.json")):
                name = p.name.removesuffix(".status.json")
                if name in PM2_STATUS_PROCESSES:
                    continue
                seen.add(name)
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    continue
                try:
                    last_seen = datetime.fromisoformat(data.get("last_seen", ""))
                    age_s = (now - last_seen).total_seconds()
                    online = age_s <= HEARTBEAT_STALE_AFTER_S
                except Exception:
                    age_s, online = None, False
                items.append({
                    "name": name,
                    "label": PROCESS_LABELS.get(name, name),
                    "online": online,
                    "last_seen": data.get("last_seen"),
                    "age_s": age_s,
                    "pid": data.get("pid"),
                    "cpu_pct": data.get("cpu_pct"),
                    "memory_mb": data.get("memory_mb"),
                })
        # Processes that are expected but have never written a single
        # heartbeat (never started, or started before this feature existed)
        # show up as "never seen" rather than silently missing from the list.
        for name, label in PROCESS_LABELS.items():
            if name in PM2_STATUS_PROCESSES:
                continue
            if name not in seen:
                items.append({
                    "name": name, "label": label, "online": False,
                    "last_seen": None, "age_s": None, "pid": None,
                    "cpu_pct": None, "memory_mb": None,
                })
        for name in PM2_STATUS_PROCESSES:
            items.append(await asyncio.to_thread(_pm2_process_status, name))
        return {"processes": sorted(items, key=lambda x: x["name"])}

    @router.get("/fdb-cache")
    async def fdb_cache_status(_=Depends(perm)):
        """State of the precomputed Agbis report cache: one row per report
        the warmer is meant to keep hot, with how old it actually is.

        This is the panel that answers "why is this page slow again" —
        a report showing as просрочен (or missing entirely) means readers
        are falling back to live Firebird queries for it.
        """
        from app.services import fdb_cache

        def _collect() -> list[dict]:
            items = []
            for report, args, tier in fdb_cache.warm_plan():
                spec = fdb_cache.TIERS[tier]
                # age_of, not peek: this runs over the whole plan every
                # 30s and only needs the timestamp, never the payload.
                age = fdb_cache.age_of(report, args)
                items.append({
                    "report": report,
                    "args": fdb_cache.encode_args(args),
                    "tier": tier,
                    "ttl_s": spec.ttl_s,
                    "refresh_s": spec.refresh_s,
                    "age_s": round(age) if age is not None else None,
                    "fresh": age is not None and age <= spec.ttl_s,
                })
            return items

        entries = await asyncio.to_thread(_collect)
        fresh = sum(1 for e in entries if e["fresh"])
        return {
            "entries": entries,
            "total": len(entries),
            "fresh": fresh,
            "stale": len(entries) - fresh,
        }

    @router.post("/process-status/{name}/restart")
    async def restart_process(name: str, _=Depends(perm)):
        """Restart one process via `pm2 restart` and notify the admin on
        Telegram once it's back online (see app/utils/restart_watcher.py —
        runs detached from this request so it survives even if `name` is
        this API server itself)."""
        pm2_name = PROCESS_TO_PM2.get(name)
        if not pm2_name:
            raise HTTPException(status_code=404, detail=f"Неизвестный процесс: {name}")
        mode = "pm2status" if name in PM2_STATUS_PROCESSES else "heartbeat"
        try:
            await asyncio.to_thread(
                _launch_restart_watcher, pm2_name, name, PROCESS_LABELS.get(name, name), mode
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Не удалось запустить рестарт: {exc}")
        return {"ok": True, "pm2_name": pm2_name}

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
                def _check():
                    conn = _connect()
                    conn.close()
                await asyncio.to_thread(_check)
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
