"""Cross-process file lock for JSON-backed repositories that get read and
rewritten wholesale (no per-record transactions) — e.g. AccessControlService,
which explicitly runs as at least two OS processes (bot + web/API) sharing
access_control.json with no other synchronization. Without this, a classic
lost-update race is trivial to hit: process A reads, process B reads (still
seeing A's pre-write state), A writes, B writes — B's write silently discards
whatever A added, with no error anywhere.

Uses atomic exclusive file creation (open(..., "x")) as the lock primitive —
this is atomic on both POSIX and Windows via the stdlib, so no extra
dependency is needed to make this actually cross-platform.

Reentrant per-thread (an outer method can call _reload(), which itself
acquires the lock internally, without deadlocking) — but NOT a substitute for
real transactional storage; this only protects the read-modify-write span
against other lock() callers, in this process or another.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path


class FileLock:
    def __init__(self, path: str | Path, timeout: float = 5.0, poll_interval: float = 0.05) -> None:
        self._lock_path = Path(str(path) + ".lock")
        self._timeout = timeout
        self._poll_interval = poll_interval
        self._local = threading.local()

    def __enter__(self) -> "FileLock":
        depth = getattr(self._local, "depth", 0)
        if depth == 0:
            self._acquire()
        self._local.depth = depth + 1
        return self

    def __exit__(self, *exc_info) -> None:
        self._local.depth -= 1
        if self._local.depth == 0:
            self._release()

    def _acquire(self) -> None:
        deadline = time.monotonic() + self._timeout
        while True:
            try:
                fd = os.open(self._lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                return
            except FileExistsError:
                if time.monotonic() >= deadline:
                    # A crashed process can leave a stale lock file behind
                    # forever — better to break it and risk one rare race
                    # than to permanently wedge every admin request.
                    try:
                        self._lock_path.unlink()
                    except OSError:
                        pass
                    continue
                time.sleep(self._poll_interval)

    def _release(self) -> None:
        try:
            self._lock_path.unlink()
        except OSError:
            pass
