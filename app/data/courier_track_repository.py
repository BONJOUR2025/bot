"""Accumulated GPS track for courier devices (StarLine «Маяк» beacons that only
expose the current position, no history). A background poller appends the current
point every few minutes; period mileage = summed distance over points in range.

Stored as {device_id: [[ts, lat, lon], ...]}. Jitter/parked points are dropped,
old points pruned, so the file stays bounded.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Optional

from app.settings import settings

DEFAULT_FILE = "courier_track.json"
MAX_AGE_DAYS = 180
MAX_POINTS = 30000
MIN_MOVE_KM = 0.02        # < 20 m from the last point → treat as parked/jitter, skip

# A single poll-to-poll jump implying more than this average speed is a bad
# GPS fix, not real driving — e.g. one point landing far from where the car
# actually was (multipath/urban-canyon glitch, or old data recorded under a
# since-fixed coordinate convention bug meeting freshly-correct data at the
# seam). Excluded from the mileage sum the same way NO_SIGNAL gaps are in
# starline_client, so one bad point doesn't blow up the period total.
MAX_SPEED_KMH = 120.0


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(min(1.0, math.sqrt(a)))


class CourierTrackRepository:
    def __init__(self, file_path: str | Path | None = None) -> None:
        self._file = Path(file_path or getattr(settings, "courier_track_file", DEFAULT_FILE))
        self._data: dict[str, list[list[float]]] = self._load()

    def _load(self) -> dict[str, list[list[float]]]:
        if not self._file.exists():
            return {}
        try:
            with open(self._file, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save(self) -> None:
        try:
            with open(self._file, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False)
        except Exception:
            pass

    def add_point(self, device_id: str, ts: float, lat: float, lon: float) -> bool:
        """Append a point unless it's within MIN_MOVE_KM of the last one (parked).
        Returns True if the point was stored."""
        key = str(device_id)
        pts = self._data.setdefault(key, [])
        if pts:
            lt, la, lo = pts[-1]
            if _haversine_km(la, lo, lat, lon) < MIN_MOVE_KM:
                return False
        pts.append([float(ts), float(lat), float(lon)])
        # prune old + cap
        cutoff = time.time() - MAX_AGE_DAYS * 86400
        if pts and pts[0][0] < cutoff:
            pts = [p for p in pts if p[0] >= cutoff]
        if len(pts) > MAX_POINTS:
            pts = pts[-MAX_POINTS:]
        self._data[key] = pts
        self._save()
        return True

    def mileage(self, device_id: str, ts_from: int, ts_to: int) -> Optional[float]:
        pts = sorted((p for p in self._data.get(str(device_id), []) if ts_from <= p[0] <= ts_to),
                     key=lambda p: p[0])
        if len(pts) < 2:
            return None
        km = 0.0
        for i in range(1, len(pts)):
            t0, lat0, lon0 = pts[i - 1]
            t1, lat1, lon1 = pts[i]
            d = _haversine_km(lat0, lon0, lat1, lon1)
            duration_h = (t1 - t0) / 3600 if t1 > t0 else None
            if duration_h and (d / duration_h) > MAX_SPEED_KMH:
                continue
            km += d
        return round(km, 1)

    def status(self, device_id: str) -> dict[str, Any]:
        pts = self._data.get(str(device_id), [])
        return {
            "points": len(pts),
            "first_ts": pts[0][0] if pts else None,
            "last_ts": pts[-1][0] if pts else None,
        }


_repo: CourierTrackRepository | None = None


def get_courier_track_repository() -> CourierTrackRepository:
    global _repo
    if _repo is None:
        _repo = CourierTrackRepository()
    return _repo
