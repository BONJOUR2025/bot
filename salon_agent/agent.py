"""Салонный аудио-агент.

Запускается на салонном ПК (Windows), к которому подключён микрофон. Держит
управляющее WebSocket-соединение с bot-app и стримит звук ТОЛЬКО когда сервер
прислал команду START — то есть пока кто-то реально слушает. Нет слушателя —
микрофон не трогается вовсе. Это не оптимизация ради трафика, а принцип
«захват только в предусмотренных ситуациях»: фонового прослушивания нет.

Поток: ffmpeg берёт микрофон через DirectShow, кодирует в Opus и упаковывает
в WebM (браузер играет WebM/Opus нативно через MediaSource). Кадры уходят на
сервер по тому же WebSocket, сервер ретранслирует их слушателям.

Устойчивость к обрыву связи — на этой стороне: управляющее соединение
переустанавливается с экспоненциальной паузой, как это сделано для бота.
Разовый обрыв сети (а на этих машинах он не редкость) не должен ронять агента.

Конфиг — salon_agent/config.json рядом (см. config.example.json). Секреты
(токен салона) только там, не в репозитории.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

try:
    import websockets
except ImportError:  # pragma: no cover
    print("нужен пакет websockets:  pip install websockets", file=sys.stderr)
    raise


CONFIG_PATH = Path(__file__).with_name("config.json")


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"нет {CONFIG_PATH} — скопируйте config.example.json и заполните",
              file=sys.stderr)
        sys.exit(1)
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def build_ffmpeg_cmd(cfg: dict) -> list[str]:
    """ffmpeg: микрофон DirectShow → Opus/WebM в stdout.

    ``device`` — точное имя устройства из
    ``ffmpeg -list_devices true -f dshow -i dummy``. Битрейт 24–32 кбит/с —
    речь чистая, канал почти не грузится.
    """
    device = cfg["mic_device"]
    bitrate = str(cfg.get("bitrate", "24k"))
    return [
        cfg.get("ffmpeg", "ffmpeg"),
        "-hide_banner", "-loglevel", "error",
        "-f", "dshow",
        "-i", f"audio={device}",
        "-ac", "1",                     # моно — речь, не музыка
        "-c:a", "libopus",
        "-b:a", bitrate,
        "-application", "voip",         # оптимизация кодека под голос
        "-f", "webm",
        # cluster'ы покороче → меньше задержка старта у слушателя
        "-cluster_time_limit", "200",
        "pipe:1",
    ]


class Streamer:
    """Пока жив — гоняет ffmpeg и шлёт его вывод в WebSocket. Останавливается
    по STOP или когда управляющее соединение падает."""

    def __init__(self, ws, cfg: dict) -> None:
        self._ws = ws
        self._cfg = cfg
        self._proc: subprocess.Popen | None = None
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._proc is not None:
            return
        cmd = build_ffmpeg_cmd(self._cfg)
        self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self._task = asyncio.create_task(self._pump())
        print("🎙 стрим начат")

    async def _pump(self) -> None:
        loop = asyncio.get_event_loop()
        assert self._proc and self._proc.stdout
        try:
            while True:
                # чтение блокирующего stdout в пуле, чтобы не вешать loop
                chunk = await loop.run_in_executor(None, self._proc.stdout.read, 4096)
                if not chunk:
                    break
                await self._ws.send(chunk)
        except Exception as exc:
            print(f"⚠️ стрим оборвался: {exc}")
        finally:
            await self.stop()

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=3)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None
            print("🔇 стрим остановлен")


async def run_once(cfg: dict) -> None:
    """Одна сессия управляющего соединения: подключиться, слушать команды."""
    salon_id = cfg["salon_id"]
    base = cfg["server_ws"].rstrip("/")
    url = f"{base}/api/audio/agent/{salon_id}?token={cfg['token']}"

    async with websockets.connect(url, max_size=None, ping_interval=20) as ws:
        print(f"✅ подключён к серверу как салон {salon_id}")
        streamer = Streamer(ws, cfg)
        try:
            async for message in ws:
                # команды приходят текстом; аудио агент только шлёт, не читает
                if isinstance(message, (bytes, bytearray)):
                    continue
                try:
                    cmd = json.loads(message).get("cmd")
                except Exception:
                    continue
                if cmd == "START":
                    await streamer.start()
                elif cmd == "STOP":
                    await streamer.stop()
        finally:
            await streamer.stop()


async def main() -> None:
    cfg = load_config()
    backoff = 1.0
    while True:
        try:
            await run_once(cfg)
            backoff = 1.0  # чистое завершение — сбрасываем паузу
        except Exception as exc:
            print(f"⚠️ соединение потеряно: {exc}; переподключение через {backoff:.0f}с")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)  # экспоненциально до 30с


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
