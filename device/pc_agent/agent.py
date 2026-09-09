"""Агент наблюдения для салонных компьютеров.

Он ТОЛЬКО рассказывает о машине и ничего на ней не делает. Это не первый этап,
а свойство: здесь нет кода, исполняющего команды, поэтому даже захваченный
сервер не сможет ничего запустить на кассовом компьютере. Цена — обновлять
агента приходится тем же удалённым доступом, которым его ставили; на парке в
несколько машин это дешевле, чем держать на кассе исполнителя команд.

Ставится службой Windows, ходит наружу сам — поэтому белый адрес и проброс
портов не нужны.

Зависимости: только requests и psutil. Стандартной библиотеки не хватает для
загрузки процессора и списка процессов, а тащить больше на кассовый ПК незачем.
"""

from __future__ import annotations

import configparser
import json
import os
import socket
import sys
import time
import traceback
from pathlib import Path

import psutil
import requests

AGENT_VERSION = "0.1.0"
CONFIG_NAME = "agent.ini"
STATE_NAME = "state.json"

# Куда отступать, если сервер недоступен. Дольше пяти минут ждать незачем:
# именно молчание агента и есть главный сигнал, ради которого он ставится.
RETRY_MIN_SECONDS = 30
RETRY_MAX_SECONDS = 300


def base_dir() -> Path:
    """Каталог рядом с исполняемым файлом.

    У собранного PyInstaller-ом exe переменная __file__ указывает во временную
    папку распаковки, которая исчезает между запусками, — конфиг и состояние
    нужно класть рядом с самим exe.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def log(message: str) -> None:
    line = time.strftime("%Y-%m-%d %H:%M:%S") + "  " + message
    print(line, flush=True)
    try:
        with open(base_dir() / "agent.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass  # некуда писать — не повод падать


def read_config() -> tuple[str, str]:
    path = base_dir() / CONFIG_NAME
    if not path.exists():
        raise SystemExit("нет файла настроек " + str(path))
    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")
    server = parser.get("agent", "server", fallback="").strip().rstrip("/")
    key = parser.get("agent", "enroll_key", fallback="").strip()
    if not server or not key:
        raise SystemExit("в " + str(path) + " нужны server и enroll_key")
    return server, key


def load_token() -> str:
    try:
        return json.loads((base_dir() / STATE_NAME).read_text(encoding="utf-8")).get("token", "")
    except Exception:
        return ""


def save_token(token: str) -> None:
    (base_dir() / STATE_NAME).write_text(json.dumps({"token": token}), encoding="utf-8")


# --- сбор показателей ------------------------------------------------------
# Каждый показатель собирается отдельно и в своём try: на разных машинах и
# правах отваливаются разные куски, и один сбой не должен лишать отчёта целиком.


def disks() -> list[dict]:
    out = []
    for part in psutil.disk_partitions(all=False):
        # Пустой привод CD-ROM бросает исключение при обращении к нему.
        if "cdrom" in part.opts or not part.fstype:
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except OSError:
            continue
        out.append({
            "mount": part.mountpoint.rstrip("\\"),
            "total_gb": round(usage.total / 2 ** 30, 1),
            "free_gb": round(usage.free / 2 ** 30, 1),
            "free_percent": round(100 - usage.percent, 1),
        })
    return out


def running_processes(watch: list[str]) -> dict[str, bool]:
    if not watch:
        return {}
    wanted = {name.lower() for name in watch}
    seen = set()
    for proc in psutil.process_iter(["name"]):
        name = (proc.info.get("name") or "").lower()
        if name in wanted:
            seen.add(name)
    return {name: name.lower() in seen for name in watch}


def local_ip() -> str | None:
    """Адрес, с которого машина реально выходит в сеть.

    gethostbyname по имени хоста на машинах с несколькими интерфейсами
    возвращает что попало, поэтому спрашиваем у маршрутизации: соединение не
    устанавливается, датаграмма никуда не уходит.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return None


def pending_reboot() -> bool | None:
    """Ждёт ли Windows перезагрузки после обновлений.

    Только на Windows и только чтение реестра; на прочих системах — None,
    чтобы панель показала прочерк, а не выдумывала «нет».
    """
    if os.name != "nt":
        return None
    try:
        import winreg
    except ImportError:
        return None
    keys = [
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending",
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired",
    ]
    for key in keys:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key):
                return True
        except OSError:
            continue
    return False


def os_version() -> str:
    import platform

    if os.name == "nt":
        return "Windows " + platform.release() + " " + platform.version()
    return platform.platform()


def collect(watch: list[str]) -> dict:
    report: dict = {
        "hostname": socket.gethostname(),
        "agent_version": AGENT_VERSION,
    }
    problems: list[str] = []

    def attempt(name, fn):
        try:
            report[name] = fn()
        except Exception as exc:
            problems.append(name + ": " + exc.__class__.__name__)

    attempt("os_version", os_version)
    attempt("uptime_seconds", lambda: int(time.time() - psutil.boot_time()))
    attempt("cpu_percent", lambda: psutil.cpu_percent(interval=1.0))
    attempt("ram_total_mb", lambda: int(psutil.virtual_memory().total / 2 ** 20))
    attempt("ram_used_percent", lambda: psutil.virtual_memory().percent)
    attempt("disks", disks)
    attempt("ip_address", local_ip)
    attempt("processes", lambda: running_processes(watch))
    attempt("pending_reboot", pending_reboot)

    # О своих сбоях агент докладывает сам: молча неполный отчёт выглядел бы как
    # исправная машина, у которой просто «нет данных».
    report["last_error"] = "; ".join(problems) or None
    return report


# --- обмен с сервером ------------------------------------------------------


def enroll(server: str, key: str) -> str:
    response = requests.post(
        server + "/api/workstations/agent/enroll",
        headers={"X-Enroll-Key": key},
        json={"hostname": socket.gethostname(), "agent_version": AGENT_VERSION},
        timeout=30,
    )
    response.raise_for_status()
    token = response.json()["token"]
    save_token(token)
    log("зарегистрирован на сервере")
    return token


def send(server: str, token: str, report: dict) -> dict:
    response = requests.post(
        server + "/api/workstations/agent/checkin",
        headers={"X-Workstation-Token": token},
        json=report,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def main() -> None:
    server, key = read_config()
    token = load_token() or enroll(server, key)
    interval = 300
    watch: list[str] = []
    failures = 0

    log("агент " + AGENT_VERSION + " запущен, сервер " + server)
    while True:
        try:
            answer = send(server, token, collect(watch))
            interval = int(answer.get("interval_seconds") or interval)
            watch = list(answer.get("watch_processes") or watch)
            failures = 0
        except requests.HTTPError as exc:
            # 401 — карточку удалили из панели: регистрируемся заново, иначе
            # агент замолчал бы навсегда и выглядел как выключенный компьютер.
            if exc.response is not None and exc.response.status_code == 401:
                log("токен отвергнут, регистрируюсь заново")
                try:
                    token = enroll(server, key)
                    continue
                except Exception:
                    log("перерегистрация не удалась: " + traceback.format_exc(limit=1).strip())
            failures += 1
        except Exception:
            failures += 1
            log("сбой отправки: " + traceback.format_exc(limit=1).strip())

        wait = interval if failures == 0 else min(
            RETRY_MIN_SECONDS * 2 ** (failures - 1), RETRY_MAX_SECONDS
        )
        time.sleep(wait)


if __name__ == "__main__":
    main()
