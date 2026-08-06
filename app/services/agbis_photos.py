"""Full-size order photos from the Agbis local-storage agent.

Where the photos actually are, since none of the obvious places hold them:

  * `DOCS_ORDER_SERV_PHOTOS.SMALL` in Firebird has a ~2.3 KB thumbnail —
    that part is easy, and it is all the database keeps. `NORMAL` (the
    full-size blob) is NULL for every photo taken since ~2019.
  * `CLOUD_PHOTO_TOKENS` describes a Google Drive target ("AgbisCloudPhoto"),
    but every credential column there is NULL, `LAST_SUCCESS_UPLOAD_DT` is
    NULL on all six workstations, and the client logs `BeCloudConnected:
    false` on every run. Nothing was ever uploaded there; it is a dead end
    that looks alive.
  * The originals live in Agbis's *local storage*: an agent process running
    on a PC in one of the salons, reachable from outside through Agbis's own
    gateway at im-gate.com. That agent is registered in `MST_AGENTS` and is
    the only row there with `LOCAL_STORAGE_STARTED` set.

The flow the Agbis client itself uses (confirmed from its rHTTP log):

    GET  https://im-gate.com/<port>/Login?User=..&Password=<sha1>&dep_id=..&AsUser=1
        -> session id (GUID)
    GET  https://im-gate.com/<port>/GetPhoto?SessionID=<guid>&FileID=<md5>
        -> the JPEG itself

`FileID` is `DOC_ORDER_SERV_PHOTOS.MD5_CHECKSUM` verbatim — verified against
production on three separate photos.

Two consequences shape this module:

1. The session id is as good as the service account's password for that
   agent, so it never leaves this process: the API proxies the bytes rather
   than handing the browser a URL it could use directly.
2. The agent is a working computer in a salon. Requests are serialised and
   cached aggressively so that browsing photos here cannot slow down the
   people serving customers there.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Optional

from app.settings import settings

logger = logging.getLogger(__name__)

# A session outlives a single photo; Agbis itself reuses one across a burst
# of downloads. Re-login is cheap (~0.6s), so this is deliberately
# conservative rather than squeezing the last minute out of it.
SESSION_TTL_S = 600
REQUEST_TIMEOUT_S = 60
# Room for one very large order to be viewed end to end without evicting
# itself; the cap is enforced after each write, oldest access first.
CACHE_SWEEP_MARGIN = 0.9


class PhotoStorageError(RuntimeError):
    """Agent unreachable, credentials rejected, or photo missing."""


@dataclass(frozen=True)
class StorageAgent:
    agent_id: int
    host: str
    port: int

    @property
    def base_url(self) -> str:
        return f"https://{self.host}/{self.port}"


_session_lock = threading.Lock()
_session: tuple[str, float] | None = None  # (session_id, expires_at)
_agent_cache: tuple[StorageAgent, float] | None = None
_AGENT_TTL_S = 3600
# One request at a time — see rule 2 in the module docstring.
_fetch_lock = threading.Lock()


def resolve_agent(force: bool = False) -> StorageAgent:
    """The local-storage agent, from MST_AGENTS.

    Read from the database rather than hardcoded: the gateway port is
    assigned by Agbis and has changed before. A hardcoded 10460 would keep
    working right up until it silently didn't.
    """
    global _agent_cache
    now = time.time()
    if not force and _agent_cache and _agent_cache[1] > now:
        return _agent_cache[0]

    from app.services.firebird_service import FIREBIRD_AVAILABLE, _connect

    if not FIREBIRD_AVAILABLE:
        raise PhotoStorageError("Firebird недоступен: драйвер fdb не установлен.")
    try:
        con = _connect()
        try:
            cur = con.cursor()
            cur.execute(
                """
                SELECT FIRST 1 id, ssh_server, ssh_port
                FROM mst_agents
                WHERE local_storage_started IS NOT NULL
                  AND ssh_server IS NOT NULL AND ssh_port IS NOT NULL
                ORDER BY local_storage_started DESC
                """
            )
            row = cur.fetchone()
        finally:
            con.close()
    except Exception as exc:
        raise PhotoStorageError(f"Не удалось определить агент хранилища: {exc}") from exc

    if row is None:
        raise PhotoStorageError(
            "В MST_AGENTS нет агента с включённым локальным хранилищем."
        )
    host = row[1].decode("utf-8", "replace") if isinstance(row[1], bytes) else str(row[1])
    agent = StorageAgent(agent_id=int(row[0]), host=host.strip(), port=int(row[2]))
    _agent_cache = (agent, now + _AGENT_TTL_S)
    return agent


def _login(agent: StorageAgent) -> str:
    import httpx

    if not settings.agbis_storage_user or not settings.agbis_storage_password_sha1:
        raise PhotoStorageError(
            "Не заданы AGBIS_STORAGE_USER / AGBIS_STORAGE_PASSWORD_SHA1."
        )
    try:
        resp = httpx.get(
            f"{agent.base_url}/Login",
            params={
                "User": settings.agbis_storage_user,
                "Password": settings.agbis_storage_password_sha1,
                "dep_id": settings.agbis_storage_dep_id,
                "AsUser": 1,
            },
            timeout=REQUEST_TIMEOUT_S,
        )
    except Exception as exc:
        raise PhotoStorageError(f"Агент хранилища недоступен: {exc}") from exc
    if resp.status_code != 200:
        raise PhotoStorageError(f"Агент отклонил вход: HTTP {resp.status_code}")

    session_id = _extract_session_id(resp.text)
    if not session_id:
        raise PhotoStorageError("Агент не вернул SessionID — проверьте учётные данные.")
    return session_id


_GUID_RE = None


def _extract_session_id(body: str) -> Optional[str]:
    """Pull the GUID out of the login response.

    Matched by shape rather than by key: the agent's reply format is not
    documented anywhere we control, and a GUID is unambiguous enough that
    this survives it being wrapped in JSON, XML or bare text.
    """
    global _GUID_RE
    if _GUID_RE is None:
        import re

        _GUID_RE = re.compile(
            r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}"
        )
    m = _GUID_RE.search(body or "")
    return m.group(0) if m else None


def _get_session(agent: StorageAgent, force_new: bool = False) -> str:
    global _session
    now = time.time()
    with _session_lock:
        if not force_new and _session and _session[1] > now:
            return _session[0]
        session_id = _login(agent)
        _session = (session_id, now + SESSION_TTL_S)
        return session_id


# ── Disk cache ────────────────────────────────────────────────────────
# Keyed by the photo's MD5, which is also its content hash — so an entry can
# never go stale and needs no invalidation. Lives outside app/ because
# deploy.ps1 mirrors that tree with robocopy /MIR and would delete it.

def _cache_dir() -> str:
    path = settings.agbis_photo_cache_dir
    os.makedirs(path, exist_ok=True)
    return path


def _cache_path(md5: str) -> str:
    return os.path.join(_cache_dir(), md5.upper())


def cache_get(md5: str) -> Optional[bytes]:
    path = _cache_path(md5)
    try:
        with open(path, "rb") as f:
            data = f.read()
    except FileNotFoundError:
        return None
    except Exception as exc:
        logger.warning(f"agbis_photos: не прочитать кэш {md5}: {exc}")
        return None
    if not data:
        return None
    try:
        os.utime(path, None)  # отметить обращение — по нему идёт вытеснение
    except Exception:
        pass
    return data


def cache_put(md5: str, data: bytes) -> None:
    path = _cache_path(md5)
    tmp = path + ".part"
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except Exception as exc:
        logger.warning(f"agbis_photos: не записать кэш {md5}: {exc}")
        try:
            os.remove(tmp)
        except Exception:
            pass
        return
    _enforce_limit()


def _enforce_limit() -> None:
    """Trim the cache to the configured cap, least-recently-used first."""
    limit = settings.agbis_photo_cache_limit_mb * 1024 * 1024
    if limit <= 0:
        return
    try:
        entries = []
        total = 0
        with os.scandir(_cache_dir()) as it:
            for e in it:
                if not e.is_file() or e.name.endswith(".part"):
                    continue
                st = e.stat()
                entries.append((st.st_atime, st.st_size, e.path))
                total += st.st_size
        if total <= limit:
            return
        # Sweep below the cap rather than to it, so a cache sitting exactly
        # at the limit doesn't trigger a delete on every single write.
        target = limit * CACHE_SWEEP_MARGIN
        for _atime, size, path in sorted(entries):
            if total <= target:
                break
            try:
                os.remove(path)
                total -= size
            except Exception:
                continue
    except Exception as exc:
        logger.warning(f"agbis_photos: очистка кэша не удалась: {exc}")


def cache_stats() -> dict:
    try:
        count = 0
        total = 0
        with os.scandir(_cache_dir()) as it:
            for e in it:
                if e.is_file() and not e.name.endswith(".part"):
                    count += 1
                    total += e.stat().st_size
        return {
            "files": count,
            "bytes": total,
            "limit_bytes": settings.agbis_photo_cache_limit_mb * 1024 * 1024,
            "dir": settings.agbis_photo_cache_dir,
        }
    except Exception as exc:
        return {"error": str(exc), "dir": settings.agbis_photo_cache_dir}


# ── Fetching ──────────────────────────────────────────────────────────

def _download(agent: StorageAgent, session_id: str, md5: str):
    import httpx

    return httpx.get(
        f"{agent.base_url}/GetPhoto",
        params={
            "SessionID": session_id,
            "dont_calc_current_size": 1,
            "FileID": md5,
        },
        timeout=REQUEST_TIMEOUT_S,
    )


def get_photo(md5: str) -> bytes:
    """Full-size JPEG for one photo, by its MD5_CHECKSUM.

    Blocking: callers in the API must go through run_with_timeout, both to
    bound the request and to keep the event loop free.
    """
    md5 = (md5 or "").strip()
    if not md5:
        raise PhotoStorageError("Не указан идентификатор фотографии.")

    cached = cache_get(md5)
    if cached is not None:
        return cached

    with _fetch_lock:
        # Another request may have fetched it while we waited for the lock.
        cached = cache_get(md5)
        if cached is not None:
            return cached

        agent = resolve_agent()
        session_id = _get_session(agent)
        try:
            resp = _download(agent, session_id, md5)
        except Exception as exc:
            raise PhotoStorageError(f"Агент хранилища недоступен: {exc}") from exc

        # A stale session comes back as an error page, not as a 401 — hence
        # the content-type check rather than a status check alone.
        if resp.status_code != 200 or not _looks_like_image(resp.content):
            session_id = _get_session(agent, force_new=True)
            try:
                resp = _download(agent, session_id, md5)
            except Exception as exc:
                raise PhotoStorageError(f"Агент хранилища недоступен: {exc}") from exc

        if resp.status_code != 200:
            raise PhotoStorageError(f"Агент вернул HTTP {resp.status_code}")
        data = resp.content
        if not _looks_like_image(data):
            raise PhotoStorageError("Агент не вернул изображение — снимка нет в хранилище.")

        cache_put(md5, data)
        return data


def _looks_like_image(data: bytes | None) -> bool:
    if not data or len(data) < 4:
        return False
    return data[:3] == b"\xff\xd8\xff" or data[:4] == b"\x89PNG"
