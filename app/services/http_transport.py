"""POST с откатом на curl.exe, когда OpenSSL не может договориться с хостом.

На боевой машине рукопожатие OpenSSL к некоторым хостам зависает: соединение
устанавливается, ClientHello уходит, а в ответ не приходит ни одного байта.
Проверено на TLS 1.0/1.1/1.2, с SNI и без, на узком и широком списке шифров —
результат одинаковый, при этом curl.exe и PowerShell (оба на schannel) с той
же машины в ту же секунду получают HTTP 200 за доли секунды.

Первым это поймали на хранилище фотографий Agbis, где сбой был постоянным и
транспорт просто перевели на curl (см. agbis_photos._curl_get). Потом
выяснилось, что к polza.ai то же самое происходит **через раз** — и это хуже
постоянного отказа: LLM-клиент молча откатывался на поиск по ключевым словам,
и снаружи выглядело как «ИИ поглупел», без единой ошибки в логе.

Поэтому здесь не замена, а подстраховка: сначала обычный httpx (быстрый путь,
без запуска процесса), и только на транспортной ошибке — повтор через curl.
Каждое срабатывание пишется в лог, чтобы частоту можно было измерить, а не
гадать.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile

log = logging.getLogger(__name__)

# Ошибки, при которых имеет смысл пробовать другой стек. Ответ сервера с любым
# HTTP-кодом сюда не попадает: 4xx/5xx — это разговор состоялся, повторять его
# другим транспортом бессмысленно.
_TRANSPORT_ERRORS = ("ConnectTimeout", "ConnectError", "ReadTimeout", "SSLError",
                     "WriteTimeout", "PoolTimeout", "RemoteProtocolError")


class HttpError(RuntimeError):
    """Запрос не удался обоими транспортами."""


def post_json(url: str, body: dict, headers: dict | None = None,
              timeout: float = 60.0, connect_timeout: float = 10.0) -> dict:
    """POST JSON → распарсенный JSON-ответ. Бросает HttpError на неуспех."""
    import httpx

    headers = dict(headers or {})
    headers.setdefault("Content-Type", "application/json")

    try:
        r = httpx.post(url, json=body, headers=headers,
                       timeout=httpx.Timeout(timeout, connect=connect_timeout))
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as exc:
        raise HttpError(f"HTTP {exc.response.status_code}: {exc.response.text[:200]}") from exc
    except Exception as exc:
        if type(exc).__name__ not in _TRANSPORT_ERRORS:
            raise
        log.warning("http_transport: httpx не смог (%s), повтор через curl: %s",
                    type(exc).__name__, url)

    status, raw = _curl_post(url, body, headers, timeout, connect_timeout)
    if status != 200:
        raise HttpError(f"HTTP {status}: {raw[:200]}")
    try:
        return json.loads(raw)
    except Exception as exc:
        raise HttpError(f"ответ не является JSON: {raw[:200]}") from exc


def _curl_post(url: str, body: dict, headers: dict,
               timeout: float, connect_timeout: float) -> tuple[int, str]:
    """Тело запроса и ответа идут через временные файлы, а не через аргументы
    и stdout: JSON бывает крупным, а смешивать его с выводом `-w %{http_code}`
    в одном потоке — напрашиваться на битый разбор."""
    fd, body_path = tempfile.mkstemp(prefix="llm_req_", suffix=".json")
    os.close(fd)
    fd, out_path = tempfile.mkstemp(prefix="llm_resp_")
    os.close(fd)
    try:
        with open(body_path, "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False)

        cmd = ["curl.exe", "-s", "--connect-timeout", str(int(connect_timeout)),
               "--max-time", str(int(timeout)), "-o", out_path, "-w", "%{http_code}"]
        for k, v in headers.items():
            cmd += ["-H", f"{k}: {v}"]
        cmd += ["--data-binary", "@" + body_path, url]

        proc = subprocess.run(cmd, capture_output=True, timeout=timeout + 15)
        code = (proc.stdout or b"").decode("ascii", "ignore").strip()
        with open(out_path, "rb") as f:
            raw = f.read().decode("utf-8", "replace")
        if not code.isdigit():
            detail = (proc.stderr or b"").decode("utf-8", "replace").strip() or f"rc={proc.returncode}"
            raise HttpError(f"curl не дошёл до ответа: {detail}")
        return int(code), raw
    finally:
        for p in (body_path, out_path):
            try:
                os.unlink(p)
            except OSError:
                pass
