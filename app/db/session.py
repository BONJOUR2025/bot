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
    _migrate_columns()
    _run_migrations()


def _migrate_columns() -> None:
    with engine.connect() as conn:
        _add_column_if_missing(conn, "payment_schedules", "objects", "TEXT DEFAULT '[]'")


def _add_column_if_missing(conn, table, column, definition):
    from sqlalchemy import text, inspect
    inspector = inspect(conn)
    if table not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns(table)}
    if column not in cols:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
        conn.commit()


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
            "ALTER TABLE telegram_messages ADD COLUMN is_ai_escalation INTEGER DEFAULT 0",
            "ALTER TABLE telegram_messages ADD COLUMN sent_by_ai INTEGER DEFAULT 0",
            "ALTER TABLE candidates ADD COLUMN follow_up_count INTEGER DEFAULT 0",
            "ALTER TABLE candidates ADD COLUMN follow_up_last_sent_at DATETIME",
            "ALTER TABLE candidates ADD COLUMN pending_interview_date TEXT",
            "ALTER TABLE candidates ADD COLUMN pending_interview_time TEXT",
            "ALTER TABLE candidates ADD COLUMN pending_interview_place TEXT",
            "ALTER TABLE candidates ADD COLUMN telegram_link_code TEXT",
            "ALTER TABLE candidates ADD COLUMN interview_notified_at DATETIME",
            "ALTER TABLE candidates ADD COLUMN is_paused INTEGER DEFAULT 0",
            "ALTER TABLE candidates ADD COLUMN interview_phase TEXT DEFAULT 'greeting'",
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
            """CREATE TABLE IF NOT EXISTS knowledge_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'Общее',
                content TEXT NOT NULL DEFAULT '',
                order_idx INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS sale_transfers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                month_key TEXT NOT NULL,
                doc_num TEXT NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0,
                from_code TEXT NOT NULL,
                to_code TEXT NOT NULL,
                from_name TEXT DEFAULT '',
                to_name TEXT DEFAULT '',
                order_date TEXT DEFAULT '',
                shoes_orders TEXT DEFAULT '',
                author TEXT DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )""",
            "CREATE INDEX IF NOT EXISTS ix_sale_transfers_month_key ON sale_transfers(month_key)",
        ]:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # column already exists
