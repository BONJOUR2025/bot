"""Restart one pm2-managed process, then watch its heartbeat file and
notify ADMIN_CHAT_ID on Telegram once it's back online.

Launched as a fully detached OS process by app/api/system.py's restart
endpoint — deliberately NOT an asyncio background task inside the API
server, because one of the three restartable processes *is* the API
server itself (bot-app): a task living there would be killed along with
the very process it's supposed to be waiting on. For the same reason
this talks to the Telegram Bot API directly over HTTP instead of going
through python-telegram-bot's Application.

Lives under app/ (not scripts/) so deploy.ps1's `robocopy app ...` step
actually ships it — that script only mirrors app/ and admin_frontend/.

Usage: python -m app.utils.restart_watcher <pm2_name> <heartbeat_name> <label> <mode>

mode is "heartbeat" (poll logs/processes/<heartbeat_name>.status.json,
used for our own processes) or "pm2status" (poll `pm2 jlist` for a
fresh pid — used for xtunnel, a compiled binary with no
write_heartbeat() call we can add to it).
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from datetime import datetime

import httpx

from app.config import ADMIN_CHAT_ID, TOKEN
from app.utils.logger import PROCESSES_LOG_DIR

# httpx logs the full request URL at INFO level by default, which would
# put the bot token in plaintext into restart_watcher.log.
logging.getLogger("httpx").setLevel(logging.WARNING)

POLL_INTERVAL_S = 5
TIMEOUT_S = 240


TELEGRAM_SEND_ATTEMPTS = 3
TELEGRAM_SEND_TIMEOUT_S = 30
TELEGRAM_RETRY_DELAY_S = 5


def send_telegram(text: str) -> None:
    """Plain HTTP call (not python-telegram-bot's Bot/Application) — this
    process is intentionally standalone. Uses httpx (already a hard
    dependency via python-telegram-bot) rather than the stdlib ssl/urllib,
    which on this box fails TLS verification against api.telegram.org —
    it builds the cert chain from the Windows system store, which is
    missing an intermediate; httpx bundles certifi's own CA list instead
    and doesn't hit the same gap.

    Retries a few times: observed one real handshake taking >15s on this
    box (freshly-spawned process, first outbound connection) — a single
    short-timeout attempt would silently drop the one notification this
    whole script exists to deliver."""
    if not TOKEN or TOKEN == "dummy" or not ADMIN_CHAT_ID:
        print(f"[restart_watcher] Telegram not configured, would have sent: {text}")
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    last_error: Exception | None = None
    for attempt in range(1, TELEGRAM_SEND_ATTEMPTS + 1):
        try:
            resp = httpx.post(url, data={"chat_id": ADMIN_CHAT_ID, "text": text}, timeout=TELEGRAM_SEND_TIMEOUT_S)
            resp.raise_for_status()
            return
        except Exception as exc:
            last_error = exc
            print(f"[restart_watcher] Telegram send attempt {attempt}/{TELEGRAM_SEND_ATTEMPTS} failed: {exc}")
            if attempt < TELEGRAM_SEND_ATTEMPTS:
                time.sleep(TELEGRAM_RETRY_DELAY_S)
    print(f"[restart_watcher] Giving up on Telegram notification after {TELEGRAM_SEND_ATTEMPTS} attempts: {last_error}")


def _pm2_status(pm2_name: str) -> tuple[str | None, int | None]:
    """(status, pid) for one pm2 process, or (None, None) if it can't be read."""
    try:
        result = subprocess.run(
            ["pm2", "jlist"], shell=True, capture_output=True,
            encoding="utf-8", errors="replace", timeout=15,
        )
        procs = json.loads(result.stdout)
        proc = next((p for p in procs if p.get("name") == pm2_name), None)
        if proc is None:
            return None, None
        return (proc.get("pm2_env") or {}).get("status"), proc.get("pid")
    except Exception:
        return None, None


def _wait_heartbeat(heartbeat_name: str, trigger_time: datetime) -> bool:
    status_path = PROCESSES_LOG_DIR / f"{heartbeat_name}.status.json"
    deadline = time.monotonic() + TIMEOUT_S
    while time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL_S)
        try:
            data = json.loads(status_path.read_text(encoding="utf-8"))
            last_seen = datetime.fromisoformat(data["last_seen"])
        except Exception:
            continue
        if last_seen > trigger_time:
            print(f"[restart_watcher] back online (heartbeat) at {last_seen.isoformat()}")
            return True
    return False


def _wait_pm2status(pm2_name: str, old_pid: int | None) -> bool:
    deadline = time.monotonic() + TIMEOUT_S
    while time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL_S)
        status, pid = _pm2_status(pm2_name)
        if status == "online" and pid is not None and pid != old_pid:
            print(f"[restart_watcher] back online (pm2 status) pid={pid} (was {old_pid})")
            return True
    return False


def main() -> None:
    # stdout/stderr here are redirected to a log file by the parent process;
    # Python still picks their text encoding from the Windows console
    # codepage (cp1251) unless told otherwise, which can't represent the
    # emoji/guillemets in the notification text below.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    pm2_name, heartbeat_name, label, mode = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    trigger_time = datetime.now()
    print(f"[restart_watcher] Restarting {pm2_name} ({label}, mode={mode}) at {trigger_time.isoformat()}")

    old_pid = None
    if mode == "pm2status":
        _, old_pid = _pm2_status(pm2_name)

    result = subprocess.run(
        ["pm2", "restart", pm2_name], shell=True, capture_output=True,
        encoding="utf-8", errors="replace", timeout=30,
    )
    if result.returncode != 0:
        print(f"[restart_watcher] pm2 restart failed: {result.stderr}")
        send_telegram(
            f"❌ Не удалось перезапустить «{label}» (pm2 restart {pm2_name}): "
            f"{(result.stderr or result.stdout).strip()[:300]}"
        )
        return

    came_back = (
        _wait_pm2status(pm2_name, old_pid) if mode == "pm2status"
        else _wait_heartbeat(heartbeat_name, trigger_time)
    )
    if came_back:
        send_telegram(f"✅ Процесс «{label}» перезапущен (pm2 restart {pm2_name}) и снова онлайн.")
        return

    print(f"[restart_watcher] {pm2_name} did not come back within {TIMEOUT_S}s")
    send_telegram(
        f"⚠️ Процесс «{label}» перезапущен, но не вышел на связь за {TIMEOUT_S // 60} мин — проверьте вручную."
    )


if __name__ == "__main__":
    main()
