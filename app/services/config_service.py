from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict

log = logging.getLogger(__name__)


class ConfigCorruptError(RuntimeError):
    """config.json exists on disk but could not be read as a JSON object.

    Raised by the strict read paths so that a *write* never silently treats an
    unreadable file as ``{}`` and persists that emptiness back — the exact
    "load → {} → save" bug that wiped the production config once already.
    """


class ConfigService:
    """Load and save settings stored in config.json.

    Hardened against the historical clobber: a transient unreadable/half-written
    config used to be read as ``{}`` and then saved back, destroying every key.
    Protections here:

    - **Atomic writes** (temp file + ``os.replace``): a reader never observes a
      half-written file, so the corruption that triggered the cascade can't
      happen from a concurrent write.
    - **Best-effort cross-process lock** around read-modify-write, so two HR
      processes patching the same file don't interleave.
    - **Strict read on write paths** (``patch``/``load_strict``): a corrupt file
      raises instead of masquerading as empty, so a write aborts rather than
      wipes. ``load`` stays tolerant (returns ``{}``) for read-only callers.
    - **Backup** of the last valid file to ``config.json.bak`` before each write,
      plus a guard refusing to overwrite a populated config with an empty one.
    """

    def __init__(self, path: str | Path = "config.json") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ── reading ──────────────────────────────────────────────────────────
    def _read_or_raise(self) -> Dict[str, Any]:
        """Missing file → ``{}``. Corrupt/non-object file → raise."""
        if not self.path.exists():
            return {}
        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:  # JSON error, encoding error, IO error
            raise ConfigCorruptError(f"{self.path} is unreadable: {exc}") from exc
        if not isinstance(data, dict):
            raise ConfigCorruptError(f"{self.path} is not a JSON object")
        return data

    def _load_raw(self) -> Dict[str, Any]:
        """Tolerant read for read-only callers: never raises, ``{}`` on trouble."""
        try:
            return self._read_or_raise()
        except ConfigCorruptError as exc:
            log.error("config read failed, treating as empty for read-only use: %s", exc)
            return {}

    @staticmethod
    def _normalize_for_response(data: Dict[str, Any]) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(key, str):
                normalized[key.lower()] = value
            else:
                normalized[key] = value
        return normalized

    @staticmethod
    def _prepare_for_storage(data: Dict[str, Any]) -> Dict[str, Any]:
        prepared: Dict[str, Any] = {}
        for key, value in data.items():
            if not isinstance(key, str):
                continue
            prepared[key.upper()] = value
        return prepared

    def load(self) -> Dict[str, Any]:
        """Tolerant load (never raises). Use for read-only access."""
        return self._normalize_for_response(self._load_raw())

    def load_strict(self) -> Dict[str, Any]:
        """Strict load: raises ``ConfigCorruptError`` if the file is unreadable.

        Use this whenever the loaded dict will be mutated and saved back, so a
        corrupt read aborts the write instead of persisting an empty result.
        """
        return self._normalize_for_response(self._read_or_raise())

    # ── locking (best-effort, cross-process) ─────────────────────────────
    def _acquire_lock(self, *, attempts: int = 50, delay: float = 0.05):
        """Best-effort exclusive lock via an O_EXCL sidecar file. Returns the
        lock path on success or None if it couldn't be taken — callers proceed
        either way (atomic writes keep a lost lock from causing corruption)."""
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        for _ in range(attempts):
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                return lock_path
            except FileExistsError:
                # Reap a stale lock (older than ~10s) left by a crashed writer.
                try:
                    if time.time() - lock_path.stat().st_mtime > 10:
                        lock_path.unlink(missing_ok=True)
                        continue
                except OSError:
                    pass
                time.sleep(delay)
            except OSError:
                return None
        return None

    @staticmethod
    def _release_lock(lock_path) -> None:
        if lock_path is not None:
            try:
                Path(lock_path).unlink(missing_ok=True)
            except OSError:
                pass

    # ── writing ──────────────────────────────────────────────────────────
    def _backup_if_valid(self) -> None:
        """Copy the current file to ``*.bak`` only if it currently parses, so a
        good backup is never overwritten by a corrupt one."""
        if not self.path.exists():
            return
        try:
            self._read_or_raise()
        except ConfigCorruptError:
            return  # don't clobber a good .bak with the corrupt current file
        try:
            bak = self.path.with_suffix(self.path.suffix + ".bak")
            bak.write_bytes(self.path.read_bytes())
        except OSError as exc:
            log.warning("config backup failed (continuing): %s", exc)

    def _atomic_write(self, payload: Dict[str, Any]) -> None:
        fd, tmp = tempfile.mkstemp(
            dir=str(self.path.parent), prefix=".config-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)  # atomic on the same filesystem
        finally:
            try:
                if os.path.exists(tmp):
                    os.unlink(tmp)
            except OSError:
                pass

    def save(
        self,
        data: Dict[str, Any],
        *,
        already_prepared: bool = False,
        force: bool = False,
    ) -> Dict[str, Any]:
        payload = data if already_prepared else self._prepare_for_storage(data)

        # Guard: never wipe a populated config with an empty payload by accident.
        if not payload and not force:
            try:
                existing = self._read_or_raise()
            except ConfigCorruptError:
                existing = {}
            if existing:
                raise ConfigCorruptError(
                    "refusing to overwrite a non-empty config with an empty "
                    "payload (pass force=True to override)"
                )

        lock = self._acquire_lock()
        try:
            self._backup_if_valid()
            self._atomic_write(payload)
        finally:
            self._release_lock(lock)
        return self._normalize_for_response(payload)

    def patch(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Merge ``updates`` into the existing config and persist.

        Reads strictly: if the on-disk file is corrupt, this raises instead of
        starting from ``{}`` and wiping every unrelated key.
        """
        lock = self._acquire_lock()
        try:
            current = self._read_or_raise()  # strict: raise, never wipe
            current.update(self._prepare_for_storage(updates))
            self._backup_if_valid()
            self._atomic_write(current)
            return self._normalize_for_response(current)
        finally:
            self._release_lock(lock)

    async def upload(self, file_bytes: bytes) -> None:
        try:
            data = json.loads(file_bytes.decode("utf-8"))
        except Exception as exc:
            raise ValueError(f"Invalid JSON: {exc}")
        prepared = data if isinstance(data, dict) else {}
        # An explicit upload is an intentional full replace — allow empty.
        self.save(self._prepare_for_storage(prepared), already_prepared=True, force=True)
