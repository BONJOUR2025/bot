"""Поиск аккаунтов по нику (Sherlock) — страница «Поиск по нику» в админке.

Sherlock запускается **отдельным процессом**, а не импортом: он живёт в своём
venv (settings.sherlock_exe) и тянет requests/urllib3/numpy/pandas, а bot-app
работает на системном Python вместе с bot-main и bot-vk. Импортировать его
сюда — значит однажды подменить им версию requests под боевыми процессами.

Полный прогон идёт по 400+ площадкам и занимает минуты, поэтому ответ
**потоковый** (NDJSON, по строке на площадку): результат появляется по мере
ответа сайтов, а не через несколько минут тишины и таймаут прокси.
"""
from __future__ import annotations

import asyncio
import json
import re
import shlex
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .dependencies import require_permission

# Ник в URL и в аргументах командной строки. Пропускаем только то, что вообще
# может быть ником: пробелы, кавычки и служебные символы сюда попасть не
# должны, даже несмотря на то, что процесс запускается без оболочки.
USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# Строки вида "[+] GitHub: https://github.com/xxx" / "[-] Reddit: Not Found!"
FOUND_RE = re.compile(r"^\[\+\]\s+([^:]+):\s+(\S+)")
NOT_FOUND_RE = re.compile(r"^\[-\]\s+([^:]+):")
DONE_RE = re.compile(r"^\[\*\]\s+Search completed with (\d+) results")

# Прогон по всем площадкам — минуты; своя граница нужна, чтобы зависший
# процесс не остался висеть навсегда, если Sherlock не вернётся сам.
HARD_LIMIT_S = 600


class SearchInput(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    # Пустой список = все площадки из базы Sherlock.
    sites: list[str] = Field(default_factory=list)
    # Через наш же vpn-proxy: часть площадок из РФ напрямую не открывается.
    use_proxy: bool = False
    # Секунды на один сайт. 60 (дефолт Sherlock) на 400+ площадках даёт
    # слишком длинный хвост из мёртвых доменов.
    timeout: int = Field(15, ge=3, le=60)


def _sherlock_path() -> Path:
    from app.settings import settings

    return Path(settings.sherlock_exe)


def _proxy_url() -> str:
    """HTTP-инбаунд локального xray — тот же, через который ходит бот пошива."""
    from app.settings import settings

    socks = settings.vpn_socks_proxy  # socks5://127.0.0.1:10808
    port = socks.rsplit(":", 1)[-1]
    try:
        return f"http://127.0.0.1:{int(port) + 1}"
    except ValueError:
        return "http://127.0.0.1:10809"


def _build_args(payload: SearchInput) -> list[str]:
    args = [
        str(_sherlock_path()),
        payload.username,
        "--no-color",
        "--print-all",
        # Иначе Sherlock кладёт <username>.txt в рабочий каталог процесса —
        # то есть в продовую папку рядом с hr.db.
        "--no-txt",
        "--timeout",
        str(payload.timeout),
    ]
    for site in payload.sites:
        args += ["--site", site]
    if payload.use_proxy:
        args += ["--proxy", _proxy_url()]
    return args


async def _stream(payload: SearchInput) -> AsyncIterator[bytes]:
    exe = _sherlock_path()
    if not exe.exists():
        yield json.dumps(
            {"type": "error", "message": f"Sherlock не найден: {exe}"},
            ensure_ascii=False,
        ).encode() + b"\n"
        return

    args = _build_args(payload)
    yield json.dumps(
        {"type": "started", "cmd": shlex.join(args[1:])}, ensure_ascii=False
    ).encode() + b"\n"

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        # Рабочий каталог — папка самого Sherlock, чтобы любые побочные файлы
        # (если появятся) не сыпались в продовый каталог приложения.
        cwd=str(exe.parent),
    )

    checked = 0
    try:
        while True:
            try:
                raw = await asyncio.wait_for(
                    proc.stdout.readline(), timeout=HARD_LIMIT_S
                )
            except asyncio.TimeoutError:
                yield json.dumps(
                    {"type": "error", "message": "Превышен общий лимит времени"},
                    ensure_ascii=False,
                ).encode() + b"\n"
                break
            if not raw:
                break
            line = raw.decode("utf-8", "replace").rstrip()

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

            m = DONE_RE.match(line)
            if m:
                yield json.dumps(
                    {"type": "done", "found": int(m.group(1)), "checked": checked},
                    ensure_ascii=False,
                ).encode() + b"\n"
    finally:
        # Клиент мог закрыть вкладку — процесс не должен пережить запрос.
        if proc.returncode is None:
            proc.kill()
            await proc.wait()


def create_osint_router() -> APIRouter:
    router = APIRouter(
        prefix="/osint",
        tags=["OSINT"],
        dependencies=[Depends(require_permission("settings"))],
    )

    @router.get("/sites")
    async def sites() -> dict[str, Any]:
        """Список площадок из базы Sherlock — для выбора подмножества."""
        exe = _sherlock_path()
        data = exe.parent.parent / "Lib" / "site-packages" / "sherlock_project" / "resources" / "data.json"
        try:
            doc = json.loads(data.read_text(encoding="utf-8"))
        except Exception as e:
            raise HTTPException(500, f"Не удалось прочитать базу площадок: {e}")
        names = sorted(k for k in doc if not k.startswith("$"))
        return {"sites": names, "total": len(names), "available": exe.exists()}

    @router.post("/username")
    async def username(payload: SearchInput):
        if not USERNAME_RE.match(payload.username):
            raise HTTPException(
                400, "Ник может содержать только латиницу, цифры, точку, дефис и подчёркивание"
            )
        return StreamingResponse(
            _stream(payload),
            media_type="application/x-ndjson",
            # Ответ идёт минутами — буферизация промежуточным слоем убила бы
            # весь смысл потока.
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    return router
