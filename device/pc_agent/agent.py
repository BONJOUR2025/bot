"""Агент управления салонными компьютерами.

Два потока, как у агента на телефонах, и по той же причине:

* **отчёт о здоровье** — раз в несколько минут, тяжёлый (диски, процессы,
  железо);
* **длинный опрос команд** — висит на открытом запросе постоянно, поэтому
  команда доезжает за секунды, а не за интервал отчёта.

Про безопасность. Команды «выполнить произвольную строку» здесь нет: на этих
машинах касса, Firebird с продажами и Agbis. Есть закрытый набор действий, а
пути к программам для запуска и перезапуска лежат в agent.ini **на самой
машине** — сервер может лишь сослаться на имя, которое машина уже разрешила у
себя. Даже захваченный сервер не укажет произвольный файл.

Работает в сеансе пользователя (задача планировщика «при входе в систему»), а
не службой под SYSTEM: из нулевого сеанса нельзя ни показать окно, ни
заблокировать экран — изоляция сеансов Windows этого не позволяет. Цена: пока
на машине никто не вошёл, агент молчит. Для салона это честно — компьютер у
кассы в рабочее время всегда с открытым сеансом.

Зависимости: requests и psutil.
"""

from __future__ import annotations

import configparser
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

import psutil
import requests

AGENT_VERSION = "0.2.0"
CONFIG_NAME = "agent.ini"
STATE_NAME = "state.json"

# Куда отступать, если сервер недоступен. Дольше пяти минут ждать незачем:
# молчание агента и есть главный сигнал, ради которого он ставится.
RETRY_MIN_SECONDS = 30
RETRY_MAX_SECONDS = 300

# Запас поверх удержания длинного опроса: сервер отвечает ровно на hold_seconds,
# и таймаут чтения должен пережить и ответ, и медленную сеть.
POLL_TIMEOUT_MARGIN = 20

# Windows прячет консоль дочернего процесса. Иначе на кассе мигали бы чёрные
# окна при каждой команде.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def base_dir() -> Path:
    """Каталог рядом с исполняемым файлом.

    У собранного PyInstaller-ом exe переменная __file__ указывает во временную
    папку распаковки, которая исчезает между запусками, — конфиг и состояние
    нужно класть рядом с самим exe.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


_log_lock = threading.Lock()


def log(message: str) -> None:
    line = time.strftime("%Y-%m-%d %H:%M:%S") + "  " + message
    with _log_lock:
        print(line, flush=True)
        try:
            with open(base_dir() / "agent.log", "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass  # некуда писать — не повод падать


class Config:
    """Настройки агента. Пути к программам живут здесь, а не приходят с сервера."""

    def __init__(self) -> None:
        path = base_dir() / CONFIG_NAME
        if not path.exists():
            raise SystemExit("нет файла настроек " + str(path))
        parser = configparser.ConfigParser()
        parser.read(path, encoding="utf-8")
        self.server = parser.get("agent", "server", fallback="").strip().rstrip("/")
        self.enroll_key = parser.get("agent", "enroll_key", fallback="").strip()
        if not self.server or not self.enroll_key:
            raise SystemExit("в " + str(path) + " нужны server и enroll_key")
        # [apps] agbis = C:\Agbis\Agbis.exe
        self.apps = dict(parser.items("apps")) if parser.has_section("apps") else {}


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
    """Ждёт ли Windows перезагрузки после обновлений."""
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
    report: dict = {"hostname": socket.gethostname(), "agent_version": AGENT_VERSION}
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
    # Агент живёт в сеансе пользователя, поэтому сам факт его работы и есть
    # доказательство сеанса; имя пригодится оператору, чтобы понимать, кому
    # уйдёт сообщение на экран.
    report["user_session"] = True
    attempt("logged_user", lambda: os.environ.get("USERNAME") or os.getlogin())

    # О своих сбоях агент докладывает сам: молча неполный отчёт выглядел бы как
    # исправная машина, у которой просто «нет данных».
    report["last_error"] = "; ".join(problems) or None
    return report


# --- исполнение команд -----------------------------------------------------


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, capture_output=True, text=True, timeout=120, creationflags=_NO_WINDOW
    )


def _shutdown(flag: str, params: dict, what: str) -> tuple[str, str]:
    delay = int(params.get("delay_seconds") or 60)
    result = _run(["shutdown", flag, "/t", str(delay), "/c", "Обслуживание BONJOUR"])
    if result.returncode != 0:
        return "failed", (result.stderr or result.stdout).strip()[:300]
    return "done", what + " через " + str(delay) + " с"


def _message(params: dict) -> tuple[str, str]:
    """Окно с сообщением на экране пользователя.

    Через ctypes, а не msg.exe: msg.exe отсутствует в домашних редакциях
    Windows, и команда молча падала бы именно на тех машинах, где её сложнее
    всего проверить.
    """
    if os.name != "nt":
        return "failed", "только для Windows"
    import ctypes

    text = str(params.get("text") or "")
    title = str(params.get("title") or "BONJOUR")
    MB_OK, MB_ICONINFORMATION, MB_SETFOREGROUND, MB_TOPMOST = 0x0, 0x40, 0x10000, 0x40000
    flags = MB_OK | MB_ICONINFORMATION | MB_SETFOREGROUND | MB_TOPMOST
    # Окно модальное: поток исполнения команд будет ждать, пока его закроют,
    # поэтому показываем в отдельном потоке и сразу отчитываемся.
    threading.Thread(
        target=lambda: ctypes.windll.user32.MessageBoxW(0, text, title, flags),
        daemon=True,
    ).start()
    return "done", "показано"


def _restart_process(cfg: Config, params: dict) -> tuple[str, str]:
    app = str(params.get("app") or "")
    path = cfg.apps.get(app.lower())
    if not path:
        # Сервер сослался на имя, которого нет в agent.ini этой машины.
        return "failed", "программа " + app + " не разрешена на этой машине"
    exe = Path(path).name
    killed = 0
    for proc in psutil.process_iter(["name"]):
        if (proc.info.get("name") or "").lower() == exe.lower():
            try:
                proc.terminate()
                killed += 1
            except psutil.Error:
                pass
    psutil.wait_procs(
        [p for p in psutil.process_iter(["name"])
         if (p.info.get("name") or "").lower() == exe.lower()],
        timeout=10,
    )
    subprocess.Popen([path], creationflags=_NO_WINDOW)
    return "done", "остановлено процессов: " + str(killed) + ", запущено заново"


def _run_app(cfg: Config, params: dict) -> tuple[str, str]:
    app = str(params.get("app") or "")
    path = cfg.apps.get(app.lower())
    if not path:
        return "failed", "программа " + app + " не разрешена на этой машине"
    subprocess.Popen([path], creationflags=_NO_WINDOW)
    return "done", "запущено"


def _cleanup_temp() -> tuple[str, str]:
    """Чистка временных файлов. Занятые файлы пропускаем — это уборка, а не
    борьба, и падать на первом же заблокированном файле она не должна."""
    removed = 0
    freed = 0
    root = Path(tempfile.gettempdir())
    for item in root.iterdir():
        try:
            size = item.stat().st_size if item.is_file() else 0
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                item.unlink()
            removed += 1
            freed += size
        except OSError:
            continue
    return "done", "удалено объектов: " + str(removed) + ", освобождено " + str(round(freed / 2 ** 20, 1)) + " МБ"


def execute(cfg: Config, command: dict) -> tuple[str, str | None]:
    """Исполнить одну команду. Возврат — (статус, пояснение).

    Ни при каких обстоятельствах не поднимает исключение наружу: потерянная
    команда навсегда зависла бы в панели со статусом «на компьютере», и
    оператор не отличил бы её от медленной.
    """
    kind = str(command.get("type"))
    params = command.get("params") or {}
    try:
        if kind == "reboot":
            return _shutdown("/r", params, "перезагрузка")
        if kind == "shutdown":
            return _shutdown("/s", params, "выключение")
        if kind == "cancel_shutdown":
            result = _run(["shutdown", "/a"])
            if result.returncode != 0:
                return "failed", "нечего отменять"
            return "done", "отменено"
        if kind == "lock":
            if os.name != "nt":
                return "failed", "только для Windows"
            import ctypes

            ok = ctypes.windll.user32.LockWorkStation()
            return ("done", "экран заблокирован") if ok else ("failed", "система отказала")
        if kind == "logoff":
            _run(["shutdown", "/l"])
            return "done", "сеанс завершается"
        if kind == "message":
            return _message(params)
        if kind == "restart_process":
            return _restart_process(cfg, params)
        if kind == "run_app":
            return _run_app(cfg, params)
        if kind == "cleanup_temp":
            return _cleanup_temp()
        if kind == "collect_now":
            return "done", None  # отчёт уйдёт следующим кругом
        return "failed", "неизвестная команда " + kind
    except Exception as exc:
        return "failed", exc.__class__.__name__ + ": " + str(exc)[:200]


# --- обмен с сервером ------------------------------------------------------


class Agent:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.token = load_token() or self.enroll()
        self.interval = 300
        self.hold = 25
        self.watch: list[str] = []
        self.pending_acks: list[dict] = []
        self.acks_lock = threading.Lock()
        self.collect_now = threading.Event()

    def enroll(self) -> str:
        response = requests.post(
            self.cfg.server + "/api/workstations/agent/enroll",
            headers={"X-Enroll-Key": self.cfg.enroll_key},
            json={"hostname": socket.gethostname(), "agent_version": AGENT_VERSION},
            timeout=30,
        )
        response.raise_for_status()
        token = response.json()["token"]
        save_token(token)
        log("зарегистрирован на сервере")
        return token

    def take_acks(self) -> list[dict]:
        with self.acks_lock:
            acks, self.pending_acks = self.pending_acks, []
        return acks

    def add_ack(self, command_id: str, status: str, result: str | None) -> None:
        with self.acks_lock:
            self.pending_acks.append(
                {"command_id": command_id, "status": status, "result": result}
            )

    def post(self, path: str, payload: dict, timeout: int) -> dict:
        response = requests.post(
            self.cfg.server + path,
            headers={"X-Workstation-Token": self.token},
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()

    # --- поток отчётов ---
    def report_loop(self) -> None:
        failures = 0
        while True:
            acks = self.take_acks()
            try:
                payload = collect(self.watch)
                payload["acks"] = acks
                answer = self.post("/api/workstations/agent/checkin", payload, 60)
                self.interval = int(answer.get("interval_seconds") or self.interval)
                self.watch = list(answer.get("watch_processes") or self.watch)
                failures = 0
            except Exception:
                # Подтверждения не доехали — возвращаем в очередь, иначе
                # выполненная команда навсегда осталась бы «на компьютере».
                with self.acks_lock:
                    self.pending_acks = acks + self.pending_acks
                failures += 1
                log("отчёт не ушёл: " + traceback.format_exc(limit=1).strip())

            wait = self.interval if failures == 0 else min(
                RETRY_MIN_SECONDS * 2 ** (failures - 1), RETRY_MAX_SECONDS
            )
            # Команда collect_now будит поток, не дожидаясь интервала.
            self.collect_now.wait(timeout=wait)
            self.collect_now.clear()

    # --- поток команд ---
    def command_loop(self) -> None:
        failures = 0
        while True:
            acks = self.take_acks()
            try:
                answer = self.post(
                    "/api/workstations/agent/poll",
                    {"acks": acks},
                    self.hold + POLL_TIMEOUT_MARGIN,
                )
                self.hold = int(answer.get("hold_seconds") or self.hold)
                commands = answer.get("commands") or []
                failures = 0
                for command in commands:
                    status, result = execute(self.cfg, command)
                    log("команда " + str(command.get("type")) + ": " + status
                        + (" — " + result if result else ""))
                    self.add_ack(str(command.get("id")), status, result)
                    if command.get("type") == "collect_now":
                        self.collect_now.set()
                if commands:
                    # Команда меняет состояние машины — пусть панель увидит его
                    # сразу, а не через интервал отчёта.
                    self.collect_now.set()
                continue
            except requests.HTTPError as exc:
                with self.acks_lock:
                    self.pending_acks = acks + self.pending_acks
                # 401 — карточку удалили из панели: регистрируемся заново, иначе
                # агент замолчал бы навсегда и выглядел выключенным компьютером.
                if exc.response is not None and exc.response.status_code == 401:
                    log("токен отвергнут, регистрируюсь заново")
                    try:
                        self.token = self.enroll()
                        continue
                    except Exception:
                        log("перерегистрация не удалась")
                failures += 1
            except Exception:
                with self.acks_lock:
                    self.pending_acks = acks + self.pending_acks
                # Обрыв висящего запроса — штатное дело: туннель, спящая сеть.
                failures += 1

            time.sleep(min(RETRY_MIN_SECONDS * 2 ** (failures - 1), RETRY_MAX_SECONDS))


def main() -> None:
    cfg = Config()
    agent = Agent(cfg)
    log("агент " + AGENT_VERSION + " запущен, сервер " + cfg.server)
    threading.Thread(target=agent.command_loop, name="commands", daemon=True).start()
    agent.report_loop()


if __name__ == "__main__":
    main()
