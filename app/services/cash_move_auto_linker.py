"""Background task: auto-link cash movements to approved "Из кассы" payouts."""
import asyncio
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 5 * 60
DEADLINE_HOURS = 12

_task: asyncio.Task | None = None


def _parse_ts(ts: str | None) -> datetime:
    if not ts:
        return datetime.min
    try:
        return datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return datetime.min


async def _run(payout_service) -> None:
    from app.data.payout_repository import PayoutRepository
    repo = PayoutRepository()

    while True:
        try:
            cutoff = datetime.now() - timedelta(hours=DEADLINE_HOURS)
            candidates = [
                p for p in repo.load_all()
                if "кассы" in (p.get("method") or "").lower()
                and p.get("status") == "Одобрено"
                and not p.get("cash_move_id")
                and _parse_ts(p.get("timestamp")) >= cutoff
            ]
            if candidates:
                logger.info(f"[AutoLinker] {len(candidates)} candidate(s) to check")
                for p in candidates:
                    await payout_service.find_cash_move_for_payout(p["id"])
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"[AutoLinker] Error during scan: {exc}")

        await asyncio.sleep(INTERVAL_SECONDS)


def start(payout_service) -> None:
    global _task
    if _task and not _task.done():
        return
    _task = asyncio.create_task(_run(payout_service))
    logger.info("[AutoLinker] Started (interval=5 min, deadline=12 h)")


def stop() -> None:
    global _task
    if _task and not _task.done():
        _task.cancel()
    logger.info("[AutoLinker] Stopped")
