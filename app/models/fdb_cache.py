from sqlalchemy import Column, Integer, LargeBinary, String, Text

from app.db.base_class import Base


class FdbCacheEntry(Base):
    """One precomputed Firebird-backed report, shared across processes.

    Lives in hr.db rather than in process memory because the warmer
    (bot-warmer) and the process that serves the data (bot-app) are
    separate pm2 processes — an in-memory cache in either one is
    invisible to the other, so warming it would achieve nothing. It also
    means a deploy, which restarts every process, no longer throws the
    warm data away.
    """

    __tablename__ = "fdb_cache"

    key = Column(String, primary_key=True)
    report = Column(String, nullable=False, index=True)
    args_json = Column(Text, nullable=False, default="[]")
    tier = Column(String, nullable=False, default="frequent")
    # gzipped UTF-8 JSON: the masters report is ~1.9 MB raw and ~124 KB
    # gzipped, and it is re-read on every request that hits it.
    value_gz = Column(LargeBinary, nullable=False)
    computed_at = Column(String, nullable=False)
    duration_ms = Column(Integer, nullable=False, default=0)
    size_bytes = Column(Integer, nullable=False, default=0)

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "report": self.report,
            "args": self.args_json,
            "tier": self.tier,
            "computed_at": self.computed_at,
            "duration_ms": self.duration_ms,
            "size_bytes": self.size_bytes,
        }
