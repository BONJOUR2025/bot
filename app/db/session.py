from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .base_class import Base

DATABASE_URL = "sqlite:///hr.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables that don't exist yet."""
    Base.metadata.create_all(bind=engine)
    _run_migrations()


def _run_migrations() -> None:
    from sqlalchemy import text
    with engine.connect() as conn:
        for stmt in [
            "ALTER TABLE candidates ADD COLUMN age INTEGER",
            "ALTER TABLE candidates ADD COLUMN external_id TEXT",
            "ALTER TABLE candidates ADD COLUMN resume_url TEXT DEFAULT ''",
            "ALTER TABLE candidates ADD COLUMN photo_url TEXT DEFAULT ''",
            "ALTER TABLE candidates ADD COLUMN last_msg_id TEXT",
            "ALTER TABLE candidates ADD COLUMN telegram_chat_id TEXT DEFAULT ''",
            "ALTER TABLE candidates ADD COLUMN telegram_username TEXT DEFAULT ''",
            "ALTER TABLE candidates ADD COLUMN has_unread_hh_msg INTEGER DEFAULT 0",
            """CREATE TABLE IF NOT EXISTS telegram_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                candidate_id INTEGER NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
                direction TEXT NOT NULL,
                text TEXT NOT NULL DEFAULT '',
                tg_message_id TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )""",
            "ALTER TABLE telegram_messages ADD COLUMN is_read INTEGER DEFAULT 0",
            "ALTER TABLE candidates ADD COLUMN telegram_link_code TEXT",
            "ALTER TABLE vacancies ADD COLUMN knowledge_base TEXT DEFAULT ''",
            "ALTER TABLE vacancies ADD COLUMN interview_location TEXT DEFAULT ''",
            """CREATE TABLE IF NOT EXISTS unlinked_telegram_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                sender_name TEXT DEFAULT '',
                text TEXT NOT NULL DEFAULT '',
                tg_message_id TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )""",
        ]:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # column already exists
