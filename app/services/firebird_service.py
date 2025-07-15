import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

import fdb

from ..utils.logger import log


class FirebirdService:
    """Simple wrapper for Firebird queries with caching."""

    def __init__(self, dsn: str, user: str, password: str) -> None:
        self.dsn = dsn
        self.user = user
        self.password = password
        self._cache: Dict[Tuple[Any, ...], Tuple[datetime, Any]] = {}
        self._version: str | None = None

    def _connect(self) -> fdb.Connection:
        return fdb.connect(dsn=self.dsn, user=self.user, password=self.password)

    def test_connection(self) -> bool:
        try:
            with self._connect() as conn:
                conn.execute_immediate("SELECT 1 FROM RDB$DATABASE")
            return True
        except Exception as exc:
            log(f"❌ Firebird connection failed: {exc}")
            return False

    def _execute(self, query: str, params: List[Any]) -> List[dict]:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(query, params)
            columns = [c[0].lower() for c in cur.description]
            rows = [dict(zip(columns, row)) for row in cur.fetchall()]
            return rows

    async def execute(self, query: str, params: List[Any]) -> List[dict]:
        return await asyncio.to_thread(self._execute, query, params)

    async def cached_execute(
        self, key: Tuple[Any, ...], query: str, params: List[Any]
    ) -> List[dict]:
        now = datetime.utcnow()
        cached = self._cache.get(key)
        if cached and (now - cached[0]).total_seconds() < 60:
            return cached[1]
        rows = await self.execute(query, params)
        self._cache[key] = (now, rows)
        return rows

    def get_version(self) -> str | None:
        """Return Firebird server version string if available."""
        if self._version is not None:
            return self._version
        try:
            with self._connect() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT rdb$get_context('SYSTEM', 'ENGINE_VERSION') FROM rdb$database"
                )
                row = cur.fetchone()
                if row and row[0]:
                    self._version = str(row[0])
        except Exception as exc:
            log(f"❌ Failed to get Firebird version: {exc}")
            self._version = None
        return self._version
