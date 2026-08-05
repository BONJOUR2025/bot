"""Entrypoint for the Firebird cache warmer (pm2: bot-warmer).

Runs the reports listed in app/services/fdb_cache.warm_plan() on a
schedule and stores the results in the shared hr.db cache, so that the
API process never has to make a user wait for Firebird. See
app/services/fdb_cache for why this is a separate process and why
warming, rather than pooling or query tuning, is the lever that works
here.

Two rules govern how it touches the database, both of them deliberate:

1. Strictly one query at a time. This process exists to *remove* load
   from the path users are on, and the Agbis Firebird server it queries
   is the same one running the tills and order intake in the salons.
   Never more than one extra query against it, ever — the 2026-07-18
   outage was caused by concurrent /masters/works queries piling up.
2. A pause between queries, sized as a fraction of how long the previous
   one took (see PACING_RATIO). A report that costs 20 s buys the server
   a matching breather before the next one starts, so a slow Firebird
   automatically gets warmed more gently rather than harder.
"""
from __future__ import annotations

import json
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    # Match the bot/API processes: fdb + threads misbehave under the proactor loop.
    import asyncio

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.db.session import init_db
from app.services import fdb_cache
from app.utils.logger import log, write_heartbeat

logger = logging.getLogger(__name__)

HEARTBEAT_NAME = "fdb_warmer"
# How long to sleep between passes over the plan. Every entry carries its
# own tier interval, so a short pass interval just means the warmer
# notices sooner that something has come due — it does not mean more
# queries.
PASS_INTERVAL_S = 30
# Pause after each query, as a multiple of that query's own duration.
PACING_RATIO = 0.5
MIN_PAUSE_S = 1.0
MAX_PAUSE_S = 30.0
# Consecutive failed cycles before we bother the admin chat. One failure
# is usually Firebird being briefly busy; three in a row is a problem.
ALERT_AFTER_FAILURES = 3
ALERT_RENOTIFY_S = 1800
# Upper bound on a single warm query. Deliberately far above the API's own
# 55s budget — measured cold, masters.works for the current month takes
# ~163s, and that is precisely the query users must never have to run
# themselves. But it still has to be bounded: without it one wedged query
# stops the warmer forever, and going through run_with_timeout also kills
# that query's Firebird attachment rather than leaking it (the failure mode
# behind the 2026-07-18 outage).
WARM_QUERY_TIMEOUT_S = 300


def _load_telegram_creds() -> tuple[str | None, str | None]:
    """Token/chat id read live from the deployed .env and config.json, the
    same way xtunnel_healthcheck.py does it, so rotating the token doesn't
    require touching this file."""
    token = chat_id = None
    root = Path(__file__).resolve().parents[1]
    try:
        env = (root / ".env").read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^TELEGRAM_BOT_TOKEN=(.+)$", env, re.MULTILINE)
        if m:
            token = m.group(1).strip()
    except Exception:
        pass
    try:
        cfg = json.loads((root / "config.json").read_text(encoding="utf-8"))
        chat_id = cfg.get("ADMIN_CHAT_ID")
    except Exception:
        pass
    return token, chat_id


def notify(text: str) -> None:
    """Telegram alert via httpx — not curl/urllib. This box has something
    injecting a certificate that curl's schannel backend and Python's raw
    ssl module both reject; httpx (OpenSSL + certifi) works, and it is
    already a dependency of the bot processes."""
    token, chat_id = _load_telegram_creds()
    if not token or not chat_id:
        logger.warning("warmer: no Telegram credentials, alert not sent")
        return
    try:
        import httpx

        httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=15,
        )
    except Exception as exc:
        logger.warning(f"warmer: failed to send alert: {exc}")


class Warmer:
    def __init__(self) -> None:
        self.consecutive_failures = 0
        self.last_alert_at: float | None = None
        self.last_cycle: dict = {}

    def compute(self, report: str, args) -> None:
        """One warm query, bounded by WARM_QUERY_TIMEOUT_S.

        asyncio.run per query rather than one long-lived loop: these are
        seconds-to-minutes apart, so the loop setup cost is noise, and a
        fresh loop each time means a query that does wedge can't leave
        anything behind in a loop the next one has to share.
        """
        import asyncio as _asyncio

        from app.services.firebird_service import run_with_timeout

        _asyncio.run(
            run_with_timeout(fdb_cache.compute, report, args, timeout=WARM_QUERY_TIMEOUT_S)
        )

    def run_pass(self, now: datetime | None = None) -> dict:
        """One walk over the warm plan. Returns a summary for the
        heartbeat/status panel."""
        now = now or datetime.now()
        started = time.time()
        warmed = skipped = failed = 0
        busy_s = 0.0
        errors: list[str] = []

        for report, args, tier in fdb_cache.warm_plan(now):
            try:
                if not fdb_cache.is_due(report, args, tier, now):
                    skipped += 1
                    continue
            except Exception as exc:
                logger.warning(f"warmer: cannot check {report}: {exc}")
                failed += 1
                continue

            q_started = time.time()
            try:
                self.compute(report, args)
                warmed += 1
            except Exception as exc:
                failed += 1
                msg = f"{report}: {type(exc).__name__}: {exc}"
                errors.append(msg[:200])
                logger.warning(f"warmer: {msg}")
            duration = time.time() - q_started
            busy_s += duration
            # Rule 2 — see module docstring. Applied after failures too: a
            # failing query is usually a *loaded* server, which is exactly
            # when backing off matters most.
            time.sleep(max(MIN_PAUSE_S, min(MAX_PAUSE_S, duration * PACING_RATIO)))

        elapsed = time.time() - started
        return {
            "warmed": warmed,
            "skipped": skipped,
            "failed": failed,
            "cycle_s": round(elapsed, 1),
            "firebird_busy_s": round(busy_s, 1),
            "busy_pct": round(100 * busy_s / elapsed, 1) if elapsed > 0 else 0.0,
            "errors": errors[:5],
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        }

    def handle_result(self, result: dict) -> None:
        self.last_cycle = result
        # Any failing report counts, not just a wholly failed cycle: one
        # report that fails every single pass (a renamed method, a bad
        # argument) would otherwise never be reported by anything, since
        # the other reports keep succeeding around it. A one-off blip
        # still clears on the next clean cycle.
        if result["failed"]:
            self.consecutive_failures += 1
        else:
            if self.consecutive_failures >= ALERT_AFTER_FAILURES:
                notify("✅ Прогрев кэша Firebird восстановился.")
                self.last_alert_at = None
            self.consecutive_failures = 0

        if self.consecutive_failures < ALERT_AFTER_FAILURES:
            return
        now = time.time()
        if self.last_alert_at is not None and now - self.last_alert_at < ALERT_RENOTIFY_S:
            return
        self.last_alert_at = now
        detail = "\n".join(result.get("errors") or []) or "нет подробностей"
        notify(
            "⚠️ Прогрев кэша Firebird не работает.\n"
            f"Неудачных циклов подряд: {self.consecutive_failures}.\n"
            f"Отчёты по продажам и мастерам будут открываться медленно.\n\n{detail}"
        )

    def heartbeat(self) -> None:
        write_heartbeat(HEARTBEAT_NAME, **{
            k: v for k, v in self.last_cycle.items() if k != "errors"
        })


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    # The warmer may well be the first process up after a deploy, and it
    # writes to hr.db — it cannot assume the bot already created the table.
    init_db()
    log("🔥 FDB warmer started")
    warmer = Warmer()
    # Publish a heartbeat before the first (potentially long) pass, so the
    # Diagnostics panel doesn't show this process as offline while it is
    # in fact busy warming.
    warmer.heartbeat()

    while True:
        try:
            result = warmer.run_pass()
            warmer.handle_result(result)
            if result["warmed"] or result["failed"]:
                log(
                    f"🔥 warm: +{result['warmed']} ~{result['skipped']} "
                    f"!{result['failed']} за {result['cycle_s']}с "
                    f"(Firebird занят {result['busy_pct']}%)"
                )
        except Exception as exc:
            logger.exception(f"warmer: pass crashed: {exc}")
            warmer.consecutive_failures += 1
            warmer.handle_result({"warmed": 0, "skipped": 0, "failed": 1,
                                  "cycle_s": 0, "firebird_busy_s": 0, "busy_pct": 0,
                                  "errors": [str(exc)[:200]],
                                  "finished_at": datetime.now().isoformat(timespec="seconds")})
        warmer.heartbeat()
        time.sleep(PASS_INTERVAL_S)


if __name__ == "__main__":
    main()
