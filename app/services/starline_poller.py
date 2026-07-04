"""Background task: sample courier StarLine «Маяк» positions and accumulate a
track, so period mileage can be computed (the API exposes no history/odometer).
Mirrors the cash_move_auto_linker worker pattern.
"""
import asyncio
import logging

from app.utils.logger import log_job

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 15 * 60

_task: "asyncio.Task | None" = None


@log_job("starline_poller")
async def poll_once() -> int:
    """Snapshot the current position of every tracked device. Returns points stored."""
    from app.services import starline_client
    if not starline_client.is_configured():
        return 0
    from app.data.courier_plan_repository import get_courier_plan_repository
    from app.data.courier_track_repository import get_courier_track_repository
    track = get_courier_track_repository()
    stored = 0
    for dev in get_courier_plan_repository().all_device_ids():
        try:
            pos = await starline_client.get_position(dev)
            if pos and track.add_point(dev, pos["ts"], pos["lat"], pos["lon"]):
                stored += 1
        except Exception as exc:
            logger.warning("[StarLinePoller] device %s: %s", dev, exc)
    return stored


async def _run() -> None:
    while True:
        try:
            n = await poll_once()
            if n:
                logger.info("[StarLinePoller] stored %d point(s)", n)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("[StarLinePoller] error: %s", exc)
        await asyncio.sleep(INTERVAL_SECONDS)


def start() -> None:
    global _task
    if _task and not _task.done():
        return
    _task = asyncio.create_task(_run())
    logger.info("[StarLinePoller] Started (interval=15 min)")


def stop() -> None:
    global _task
    if _task and not _task.done():
        _task.cancel()
    logger.info("[StarLinePoller] Stopped")
