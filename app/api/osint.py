"""Поиск аккаунтов по нику (Maigret) — страница «Поиск по нику» в админке.

Maigret запускается **отдельным процессом**, а не импортом: он живёт в своём
venv (settings.maigret_exe) и тянет aiohttp/lxml/pillow/reportlab/flask, а
bot-app работает на системном Python вместе с bot-main и bot-vk. Импортировать
его сюда — значит однажды подменить им версию aiohttp под боевыми процессами.

Прогон идёт по сотням площадок и занимает минуты, поэтому ответ **потоковый**
(NDJSON, по строке на событие): попадания появляются по мере ответа сайтов, а
не через несколько минут тишины и таймаут прокси.

Три особенности запуска Maigret 0.6.5 на этой машине, каждая из которых по
отдельности ломает работу целиком:

* `PYTHONIOENCODING=utf-8` — иначе он падает с UnicodeEncodeError ещё на своём
  баннере: печатает «♥», а stdout процесса на Windows по умолчанию cp1251.
* `--dns-resolver threaded` — его асинхронный резолвер (aiodns) на этом боксе
  не достучался ни до одного домена: «Connecting failure (DNS)» на 100% сайтов.
  Системный резолвер работает.
* `--no-autoupdate` — на старте он лезет обновлять базу площадок (3363 сайта).
  Для сервера это лишняя сетевая зависимость на каждом запросе.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import shutil
import tempfile
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .dependencies import require_permission

# Ник уходит в аргументы командной строки и в URL. Пропускаем только то, что
# вообще может быть ником, даже несмотря на запуск без оболочки.
USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# "[+] VK: https://vk.com/xxx" — найдено; "[-] Reddit: Not found" — нет.
FOUND_RE = re.compile(r"^\[\+\]\s+(.+?):\s+(https?://\S+)")
NOT_FOUND_RE = re.compile(r"^\[-\]\s+(.+?):\s+Not found!?$")
# Итоговая строка короткого отчёта Maigret.
TOTAL_RE = re.compile(r"returned (\d+) accounts")

# Своя граница, чтобы зависший процесс не остался висеть навсегда.
HARD_LIMIT_S = 900


class SearchInput(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    # Сколько площадок из базы брать (по рангу). 0 = все.
    top_sites: int = Field(50, ge=0, le=5000)
    # Через наш же vpn-proxy: часть площадок из РФ напрямую не открывается.
    use_proxy: bool = False
    timeout: int = Field(12, ge=3, le=60)


def _maigret_path() -> Path:
    from app.settings import settings

    return Path(settings.maigret_exe)


def _proxy_url() -> str:
    """HTTP-инбаунд локального xray — тот же, через который ходит бот пошива."""
    from app.settings import settings

    port = settings.vpn_socks_proxy.rsplit(":", 1)[-1]
    try:
        return f"http://127.0.0.1:{int(port) + 1}"
    except ValueError:
        return "http://127.0.0.1:10809"


def _build_args(payload: SearchInput, report_dir: str) -> list[str]:
    args = [
        str(_maigret_path()),
        payload.username,
        "--no-color",
        "--no-progressbar",
        "--no-autoupdate",
        "--dns-resolver",
        "threaded",
        "--print-not-found",
        "--timeout",
        str(payload.timeout),
        # Отчёт кладём во временную папку, а не в рабочий каталог процесса
        # (это продовая папка рядом с hr.db). Из него берём то, чего нет в
        # консоли: извлечённые идентификаторы и теги площадок.
        "-J",
        "simple",
        "--folderoutput",
        report_dir,
    ]
    if payload.top_sites:
        args += ["--top-sites", str(payload.top_sites)]
    else:
        args += ["-a"]
    if payload.use_proxy:
        args += ["--proxy", _proxy_url()]
    return args


def _read_report(report_dir: str) -> dict[str, Any]:
    """Досье из JSON-отчёта: по каждой найденной площадке — извлечённые
    идентификаторы и теги. Именно этим Maigret отличается от простого
    «занят/свободен»."""
    details: dict[str, Any] = {}
    try:
        for path in Path(report_dir).glob("*.json"):
            doc = json.loads(path.read_text(encoding="utf-8"))
            for site, entry in doc.items():
                status = (entry or {}).get("status") or {}
                if status.get("status") != "Claimed":
                    continue
                details[site] = {
                    "url": entry.get("url_user"),
                    "ids": status.get("ids") or {},
                    "tags": status.get("tags") or [],
                    "rank": entry.get("rank"),
                }
    except Exception:
        # Отчёт — приятное дополнение; из-за него поиск падать не должен.
        return details
    return details


async def _stream(payload: SearchInput) -> AsyncIterator[bytes]:
    exe = _maigret_path()
    if not exe.exists():
        yield json.dumps(
            {"type": "error", "message": f"Maigret не найден: {exe}"},
            ensure_ascii=False,
        ).encode() + b"\n"
        return

    report_dir = tempfile.mkdtemp(prefix="maigret-")
    args = _build_args(payload, report_dir)
    yield json.dumps(
        {"type": "started", "cmd": shlex.join(args[1:])}, ensure_ascii=False
    ).encode() + b"\n"

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=report_dir,
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
    )

    checked = 0
    total: int | None = None
    try:
        while True:
            try:
                raw = await asyncio.wait_for(proc.stdout.readline(), timeout=HARD_LIMIT_S)
            except asyncio.TimeoutError:
                yield json.dumps(
                    {"type": "error", "message": "Превышен общий лимит времени"},
                    ensure_ascii=False,
                ).encode() + b"\n"
                break
            if not raw:
                break
            # strip(), а не rstrip(): Maigret перерисовывает прогресс и шлёт
            # строки с ведущим возвратом каретки — с ним якорь "^[" в
            # регулярках не срабатывает, и разбор молча даёт ноль результатов.
            line = raw.decode("utf-8", "replace").strip()

            m = FOUND_RE.match(line)
            if m:
                checked += 1
                yield json.dumps(
                    {"type": "hit", "site": m.group(1).strip(), "url": m.group(2), "n": checked},
                    ensure_ascii=False,
                ).encode() + b"\n"
                continue

            m = NOT_FOUND_RE.match(line)
            if m:
                checked += 1
                yield json.dumps(
                    {"type": "miss", "site": m.group(1).strip(), "n": checked},
                    ensure_ascii=False,
                ).encode() + b"\n"
                continue

            m = TOTAL_RE.search(line)
            if m:
                total = int(m.group(1))

        await proc.wait()
        yield json.dumps(
            {
                "type": "done",
                "found": total,
                "checked": checked,
                "details": _read_report(report_dir),
            },
            ensure_ascii=False,
        ).encode() + b"\n"
    finally:
        # Клиент мог закрыть вкладку — процесс не должен пережить запрос.
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
        shutil.rmtree(report_dir, ignore_errors=True)


def create_osint_router() -> APIRouter:
    router = APIRouter(
        prefix="/osint",
        tags=["OSINT"],
        dependencies=[Depends(require_permission("settings"))],
    )

    @router.get("/sites")
    async def sites() -> dict[str, Any]:
        """Размер базы площадок — для подписей в интерфейсе."""
        exe = _maigret_path()
        # Maigret держит базу в профиле пользователя и обновляет её сам;
        # в пакете лежит только та, что приехала с релизом.
        candidates = [
            Path.home() / ".maigret" / "data.json",
            exe.parent.parent / "Lib" / "site-packages" / "maigret" / "resources" / "data.json",
        ]
        for path in candidates:
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            sites_doc = doc.get("sites", doc)
            return {
                "total": len(sites_doc),
                "available": exe.exists(),
                "database": str(path),
            }
        raise HTTPException(500, "База площадок Maigret не найдена")

    @router.post("/username")
    async def username(payload: SearchInput):
        if not USERNAME_RE.match(payload.username):
            raise HTTPException(
                400,
                "Ник может содержать только латиницу, цифры, точку, дефис и подчёркивание",
            )
        return StreamingResponse(
            _stream(payload),
            media_type="application/x-ndjson",
            # Ответ идёт минутами — буферизация промежуточным слоем убила бы
            # весь смысл потока.
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    return router
