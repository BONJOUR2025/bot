"""API страницы «Бот пошива»: настройки и диагностика стороннего бота,
который тянет заказы индивидуального пошива из Агбиса в amoCRM.

Сам бот лежит вне этого репозитория (settings.poshiv_bot_dir, рабочий стол)
и деплоем не мирроится, поэтому здесь только чтение его состояния и запись
оверлея настроек — кода бота мы отсюда не трогаем.

Статус процесса (online/pid/память) и кнопка перезапуска живут в общем
мониторинге (app/api/system.py, процесс poshiv_bot) — дублировать их тут
незачем. Этот роутер отвечает на то, чего общий мониторинг не знает: не
протух ли токен amoCRM, кто назначен мастером и куда уходит заказ после
готовности.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .dependencies import require_permission

SETTINGS_FILENAME = "poshiv_settings.json"
TOKENS_FILENAME = "amo_tokens.json"
CONFIG_FILENAME = "config.py"
# Своего лог-файла у бота нет — stderr забирает pm2, отсюда и читаем.
PM2_LOG = Path.home() / ".pm2" / "logs" / "poshiv-bot-error.log"


def _bot_dir() -> Path:
    from app.settings import settings

    return Path(settings.poshiv_bot_dir)


def _settings_path() -> Path:
    return _bot_dir() / SETTINGS_FILENAME


def _read_overlay() -> dict[str, Any]:
    try:
        return json.loads(_settings_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception:
        # Битый файл не должен ронять страницу: бот в этом случае тоже молча
        # работает на дефолтах — см. config._apply_overlay у бота.
        return {}


def _parse_config_defaults() -> dict[str, Any]:
    """Дефолты из config.py бота — без импорта самого модуля.

    Импортировать его нельзя: он тянет свои зависимости, свой рабочий каталог
    и сам накатывает оверлей, а нам нужны именно исходные значения из кода,
    чтобы показать их как «по умолчанию». Файл правится руками раз в полгода,
    поэтому читаем текстом — это дешевле песочницы с подпроцессом.
    """
    stages: list[dict[str, Any]] = []
    check_time = ""
    managers: list[int] = []
    try:
        text = (_bot_dir() / CONFIG_FILENAME).read_text(encoding="utf-8")
    except Exception:
        return {"stages": stages, "check_time": check_time, "manager_ids": managers}

    m = re.search(r'^CHECK_TIME\s*=\s*"([^"]+)"', text, re.M)
    if m:
        check_time = m.group(1)

    m = re.search(r"^MANAGER_IDS\s*=\s*\[([^\]]*)\]", text, re.M)
    if m:
        managers = [int(x) for x in re.findall(r"\d+", m.group(1))]

    block = re.search(r"^STAGES\s*=\s*\{(.*?)^\}", text, re.M | re.S)
    if block:
        for line in block.group(1).splitlines():
            key = re.match(r'\s*"([^"]+)"\s*:\s*\{', line)
            if not key:
                continue
            label = re.search(r'"label"\s*:\s*"([^"]*)"', line)
            nxt = re.search(r'"next"\s*:\s*(?:"([^"]*)"|None)', line)
            stages.append({
                "key": key.group(1),
                "label": label.group(1) if label else key.group(1),
                "next": nxt.group(1) if nxt and nxt.group(1) else None,
            })
    return {"stages": stages, "check_time": check_time, "manager_ids": managers}


def _amo_token_state() -> dict[str, Any]:
    """Срок жизни токена amoCRM.

    Отдельный показатель, потому что протухший токен выглядит для оператора
    ровно как «бот сломался»: процесс online, Telegram отвечает, а сделки
    в амо не двигаются.
    """
    try:
        data = json.loads((_bot_dir() / TOKENS_FILENAME).read_text(encoding="utf-8"))
    except Exception:
        return {"ok": False, "expires_at": None, "hours_left": None,
                "detail": "amo_tokens.json не прочитан"}
    exp = data.get("expires_at")
    if not exp:
        return {"ok": False, "expires_at": None, "hours_left": None,
                "detail": "в файле нет expires_at"}
    left = (exp - time.time()) / 3600
    return {
        "ok": left > 0,
        "expires_at": datetime.fromtimestamp(exp).isoformat(timespec="seconds"),
        "hours_left": round(left, 1),
        "detail": "" if left > 0 else "истёк — бот обновит его при первом обращении",
    }


def _log_tail(limit: int = 40) -> list[str]:
    """Последние строки лога бота.

    Бот логирует юникод экранированными последовательностями, и в файл они
    попадают буквально — без обратного раскодирования в интерфейсе была бы
    каша из экранов вместо рамок и эмодзи. Ниже это разворачивается обратно.

    Русский текст самого бота местами уже испорчен в самом файле: pm2 пишет
    его через кодировку консоли и роняет часть символов в U+FFFD. Вернуть их
    нельзя, поэтому читаем как utf-8 и показываем как есть.
    """
    try:
        raw = PM2_LOG.read_bytes().decode("utf-8", "replace").splitlines()
    except Exception:
        return []
    out: list[str] = []
    for line in raw[-limit:]:
        try:
            out.append(
                re.sub(
                    r"\\u[0-9a-fA-F]{4}|\\U[0-9a-fA-F]{8}",
                    lambda m: chr(int(m.group(0)[2:], 16)),
                    line,
                )
            )
        except Exception:
            out.append(line)
    return out


class SettingsInput(BaseModel):
    manager_ids: list[int] | None = None
    masters: dict[str, int | None] | None = None
    check_time: str | None = None
    stage_next: dict[str, str | None] | None = None


def create_poshiv_bot_router() -> APIRouter:
    router = APIRouter(
        prefix="/poshiv-bot",
        tags=["Бот пошива"],
        dependencies=[Depends(require_permission("settings"))],
    )

    @router.get("/settings")
    async def get_settings():
        defaults = _parse_config_defaults()
        overlay = _read_overlay()
        effective_next = {s["key"]: s["next"] for s in defaults["stages"]}
        effective_next.update({
            k: v for k, v in (overlay.get("stage_next") or {}).items()
            if k in effective_next
        })
        return {
            "bot_dir": str(_bot_dir()),
            "settings_file": str(_settings_path()),
            "has_overlay": bool(overlay),
            "stages": defaults["stages"],
            "effective": {
                "manager_ids": overlay.get("manager_ids") or defaults["manager_ids"],
                "masters": overlay.get("masters") or {},
                "check_time": overlay.get("check_time") or defaults["check_time"],
                "stage_next": effective_next,
            },
            "defaults": defaults,
        }

    @router.put("/settings")
    async def put_settings(payload: SettingsInput):
        defaults = _parse_config_defaults()
        stage_keys = {s["key"] for s in defaults["stages"]}
        if not stage_keys:
            raise HTTPException(500, "Не удалось прочитать config.py бота пошива")
        doc = _read_overlay()

        if payload.check_time is not None:
            if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", payload.check_time):
                raise HTTPException(400, "Время проверки должно быть в формате ЧЧ:ММ")
            doc["check_time"] = payload.check_time

        if payload.manager_ids is not None:
            if not payload.manager_ids:
                raise HTTPException(400, "Список руководителей не может быть пустым")
            doc["manager_ids"] = payload.manager_ids

        if payload.masters is not None:
            unknown = set(payload.masters) - stage_keys
            if unknown:
                raise HTTPException(
                    400, "Неизвестные этапы: " + ", ".join(sorted(unknown))
                )
            # Пустое значение = мастер не назначен. Этап продолжает работать,
            # просто без уведомления: несуществующий id раньше ронял отправку
            # и обрывал обработчик смены этапа уже после перевода сделки.
            doc["masters"] = {k: v for k, v in payload.masters.items() if v}

        if payload.stage_next is not None:
            for src, dst in payload.stage_next.items():
                if src not in stage_keys:
                    raise HTTPException(400, "Неизвестный этап: " + src)
                if dst and dst not in stage_keys:
                    raise HTTPException(400, "Неизвестный следующий этап: " + dst)
                if dst and dst == src:
                    raise HTTPException(
                        400, "Этап «" + src + "» не может вести сам в себя"
                    )
            doc["stage_next"] = payload.stage_next

        path = _settings_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as e:
            raise HTTPException(500, "Не удалось сохранить настройки: " + str(e))
        # Бот читает конфиг только на старте, поэтому явно говорим, что нужен
        # перезапуск — иначе оператор сохранит и будет ждать эффекта впустую.
        return {"saved": True, "restart_required": True, "settings": doc}

    @router.get("/health")
    async def health():
        import asyncio

        from app.api.system import _pm2_process_status

        process = await asyncio.to_thread(_pm2_process_status, "poshiv_bot")
        return {
            "process": process,
            "amo_token": _amo_token_state(),
            "log_tail": _log_tail(),
        }

    return router
