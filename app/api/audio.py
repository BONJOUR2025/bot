"""Живое прослушивание микрофонов салонов.

Модель — открытый аудиоконтроль рабочих процессов по ст. 214.2/86 ТК РФ:
основание, цель и порядок фиксируются в ЛНА работодателя, работники
ознакомлены под подпись, посетители уведомлены. Технически это здесь
поддержано тремя вещами, которые снижают правовой и приватностный след:

1. Доступ — только под правом ``salon-audio`` и под аудит-логом: кто, когда
   и какой салон слушал, пишется в audio_listen_log.json. Круг лиц ограничен,
   как и требует порядок обработки ПДн.
2. Микрофон «горячий» только на время активного прослушивания. Агент на
   салонном ПК не стримит фоном — сервер сигналит ему START, когда появился
   первый слушатель, и STOP, когда ушёл последний. Это принцип «только в
   предусмотренных ситуациях»: нет слушателя — нет захвата звука.
3. Только live, ничего не хранится. Поток проходит через сервер транзитом
   в браузер и нигде не оседает.

Транспорт — WebSocket: агент шлёт Opus-в-WebM кадры, сервер ретранслирует их
подключённым слушателям того же салона. Устойчивость к обрыву связи — на
стороне агента (см. salon_agent/agent.py), сервер просто закрывает мёртвые
соединения и снимает START, когда слушателей не осталось.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.api.dependencies import require_permission
from app.config import SALON_AUDIO_TOKENS
from app.services.access_control_service import ResolvedUser, get_access_control_service
from app.utils.logger import log

# Куда пишем, кто и когда слушал. Отдельный файл в корне боевого каталога,
# рядом с остальными json-хранилищами.
_LOG_PATH = Path(__file__).resolve().parents[2] / "audio_listen_log.json"


class _SalonHub:
    """Один салон: его агент (источник) и текущие слушатели.

    Держит состояние в памяти процесса bot-app. Это осознанно: поток
    эфемерный, переживать рестарт ему незачем — слушатель просто переоткроет
    соединение. Единственное, что персистентно, — аудит-лог сессий.
    """

    def __init__(self, salon_id: str) -> None:
        self.salon_id = salon_id
        self.agent: WebSocket | None = None
        self.listeners: set[WebSocket] = set()
        self.header: bytes | None = None  # init-сегмент WebM для новых слушателей
        self._lock = asyncio.Lock()

    async def broadcast(self, chunk: bytes) -> None:
        """Раздать кадр всем слушателям, отвалившихся — вычистить."""
        dead = []
        for ws in list(self.listeners):
            try:
                await ws.send_bytes(chunk)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.listeners.discard(ws)


class _AudioBus:
    def __init__(self) -> None:
        self._salons: dict[str, _SalonHub] = {}
        self._lock = asyncio.Lock()

    def hub(self, salon_id: str) -> _SalonHub:
        hub = self._salons.get(salon_id)
        if hub is None:
            hub = _SalonHub(salon_id)
            self._salons[salon_id] = hub
        return hub


_bus = _AudioBus()


def _append_log(entry: dict) -> None:
    """Аудит прослушивания. Никогда не роняет запрос — только предупреждает."""
    try:
        data = []
        if _LOG_PATH.exists():
            data = json.loads(_LOG_PATH.read_text(encoding="utf-8") or "[]")
        data.append(entry)
        _LOG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:  # pragma: no cover
        log(f"⚠️ [audio] не удалось записать аудит прослушивания: {exc}")


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


async def _signal_agent(hub: _SalonHub, command: str) -> None:
    """START/STOP агенту: включай/выключай микрофон. Агент стримит только
    когда есть кто слушать — фонового захвата нет."""
    if hub.agent is None:
        return
    try:
        await hub.agent.send_text(json.dumps({"cmd": command}))
    except Exception:
        pass


def create_audio_router() -> APIRouter:
    router = APIRouter()

    @router.websocket("/audio/agent/{salon_id}")
    async def agent_endpoint(ws: WebSocket, salon_id: str) -> None:
        """Салонный агент. Авторизуется общим для салона токеном (не сессией
        админа): токены заданы в конфиге боевого каталога, не в репозитории."""
        token = ws.query_params.get("token", "")
        expected = SALON_AUDIO_TOKENS.get(salon_id)
        if not expected or token != expected:
            await ws.close(code=4401)
            log(f"⚠️ [audio] агент {salon_id}: неверный токен, отклонён")
            return

        await ws.accept()
        hub = _bus.hub(salon_id)
        hub.agent = ws
        hub.header = None
        log(f"🎙 [audio] агент подключён: салон {salon_id}")
        # Если слушатели уже ждут — сразу просим начать поток.
        if hub.listeners:
            await _signal_agent(hub, "START")
        try:
            while True:
                msg = await ws.receive()
                if msg["type"] == "websocket.disconnect":
                    break
                data = msg.get("bytes")
                if data is None:
                    continue
                # Первый кадр WebM — инициализационный сегмент; храним его,
                # чтобы отдавать новым слушателям, подключившимся в середине.
                if hub.header is None:
                    hub.header = data
                await hub.broadcast(data)
        except WebSocketDisconnect:
            pass
        except Exception as exc:  # pragma: no cover
            log(f"⚠️ [audio] агент {salon_id} оборвался: {exc}")
        finally:
            if hub.agent is ws:
                hub.agent = None
                hub.header = None
            log(f"🎙 [audio] агент отключён: салон {salon_id}")

    @router.websocket("/audio/listen/{salon_id}")
    async def listen_endpoint(ws: WebSocket, salon_id: str) -> None:
        """Браузер админа. Авторизация — по тому же токену сессии (cookie
        access_token или ?token=), плюс проверка права salon-audio."""
        token = ws.query_params.get("token") or ws.cookies.get("access_token")
        user = None
        if token:
            try:
                user = get_access_control_service().verify_token(token)
            except Exception:
                user = None
        if user is None:
            await ws.close(code=4401)
            return
        if "salon-audio" not in user.permissions and "*" not in user.permissions:
            await ws.close(code=4403)
            log(f"⚠️ [audio] {user.login}: нет права salon-audio, отказ по салону {salon_id}")
            return

        who = user.display_name or user.login

        await ws.accept()
        hub = _bus.hub(salon_id)
        first_listener = not hub.listeners
        hub.listeners.add(ws)

        started_at = time.time()
        _append_log({
            "event": "listen_start",
            "salon_id": salon_id,
            "user_id": user.id,
            "user_name": who,
            "at": _now(),
        })
        log(f"🔊 [audio] {who} слушает салон {salon_id}")

        # Первый слушатель — будим агента (включаем микрофон).
        if first_listener:
            await _signal_agent(hub, "START")
        # Отдаём init-сегмент, если агент уже прислал (иначе браузер не
        # соберёт поток, подключившись в середине).
        if hub.header is not None:
            try:
                await ws.send_bytes(hub.header)
            except Exception:
                pass

        try:
            while True:
                # Слушатель ничего не шлёт; ждём только его отключения.
                msg = await ws.receive()
                if msg["type"] == "websocket.disconnect":
                    break
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            hub.listeners.discard(ws)
            _append_log({
                "event": "listen_stop",
                "salon_id": salon_id,
                "user_id": user.id,
                "user_name": who,
                "at": _now(),
                "duration_sec": round(time.time() - started_at, 1),
            })
            log(f"🔇 [audio] {who} перестал слушать салон {salon_id} "
                f"({round(time.time() - started_at)}с)")
            # Ушёл последний — гасим микрофон на салоне. И сбрасываем
            # кешированный init-сегмент: следующий сеанс агент начнёт НОВЫМ
            # ffmpeg-потоком с новым WebM-заголовком, а старый заголовок не
            # подходит к новым кластерам (браузер играл бы 1-2 сек и глох).
            if not hub.listeners:
                hub.header = None
                await _signal_agent(hub, "STOP")

    @router.get("/audio/salons/{salon_id}/status")
    async def status(
        salon_id: str,
        user: ResolvedUser = Depends(require_permission("salon-audio")),
    ) -> dict:
        """Онлайн ли агент салона и сколько сейчас слушателей (для UI-индикации
        доступности кнопки «слушать»). Под тем же правом, что и прослушивание."""
        hub = _bus.hub(salon_id)
        return {
            "salon_id": salon_id,
            "agent_online": hub.agent is not None,
            "listeners": len(hub.listeners),
        }

    return router
