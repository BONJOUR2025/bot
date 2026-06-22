from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from .base_class import Base

DATABASE_URL = "sqlite:///hr.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _):
    """Enable WAL mode so the bot process and the API process can safely
    read/write the same DB concurrently without blocking each other."""
    cur = dbapi_connection.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.close()


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
    _seed_hiring_strategies()
    _migrate_recruitment_kb_and_strategy_defaults()


def _migrate_columns() -> None:
    with engine.connect() as conn:
        _add_column_if_missing(conn, "payment_schedules", "objects", "TEXT DEFAULT '[]'")
        _add_column_if_missing(conn, "payment_schedules", "seller", "TEXT DEFAULT ''")
        _add_column_if_missing(conn, "payment_schedules", "pay_from", "TEXT DEFAULT ''")
        _add_column_if_missing(conn, "payment_schedules", "invoice_file_url", "TEXT DEFAULT ''")
        _add_column_if_missing(conn, "sale_transfers", "to_category", "TEXT")


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
            "ALTER TABLE vacancies ADD COLUMN strategy_id INTEGER",
            "ALTER TABLE vacancies ADD COLUMN extra_instructions TEXT DEFAULT ''",
            "ALTER TABLE candidates ADD COLUMN pending_decline_suggested_at DATETIME",
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
            """CREATE TABLE IF NOT EXISTS assets (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id   TEXT    NOT NULL,
                employee_name TEXT    DEFAULT '',
                position      TEXT    DEFAULT '',
                item_name     TEXT    NOT NULL DEFAULT '',
                size          TEXT    DEFAULT '',
                quantity      INTEGER DEFAULT 1,
                issue_date    TEXT    NOT NULL DEFAULT '',
                return_date   TEXT,
                service_life  INTEGER,
                notified_at   TEXT,
                acked_at      TEXT,
                created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
            )""",
            "CREATE INDEX IF NOT EXISTS ix_assets_employee_id ON assets(employee_id)",
        ]:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # column already exists
    _migrate_assets_from_json()


def _migrate_assets_from_json() -> None:
    """One-time migration of assets.json into the assets table."""
    import json as _json
    import os as _os
    try:
        from app.settings import settings as _s
        json_file = _s.assets_file
    except Exception:
        json_file = "assets.json"
    if not _os.path.exists(json_file):
        return
    from sqlalchemy import text
    with engine.connect() as conn:
        if conn.execute(text("SELECT COUNT(*) FROM assets")).scalar() > 0:
            return  # already populated — nothing to do
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            data = _json.load(f)
    except Exception:
        return
    if not data:
        return
    with engine.begin() as conn:
        for item in data:
            conn.execute(text("""
                INSERT OR IGNORE INTO assets
                    (id, employee_id, employee_name, position, item_name, size,
                     quantity, issue_date, return_date, service_life,
                     notified_at, acked_at)
                VALUES
                    (:id, :employee_id, :employee_name, :position, :item_name, :size,
                     :quantity, :issue_date, :return_date, :service_life,
                     :notified_at, :acked_at)
            """), {
                "id":            item.get("id"),
                "employee_id":   str(item.get("employee_id", "")),
                "employee_name": item.get("employee_name", ""),
                "position":      item.get("position", ""),
                "item_name":     item.get("item_name", ""),
                "size":          item.get("size", ""),
                "quantity":      item.get("quantity", 1),
                "issue_date":    item.get("issue_date", ""),
                "return_date":   item.get("return_date") or None,
                "service_life":  item.get("service_life") or None,
                "notified_at":   item.get("notified_at") or None,
                "acked_at":      item.get("acked_at") or None,
            })
    try:
        from app.utils.logger import log
        log(f"✅ Migrated {len(data)} assets from {json_file} to DB")
    except Exception:
        pass


_BUILTIN_STRATEGIES = [
    dict(
        name="Стандартный отбор",
        description="Без автоматических фильтров и без агрессивных сроков. Безопасный вариант по умолчанию.",
        is_builtin=True,
        follow_up_enabled=False,
        follow_up_delay_hours=24,
        decline_after_hours=None,
    ),
    dict(
        name="Быстрый найм",
        description="Короткие сроки напоминаний, предложение отказа через 48ч без ответа (требует подтверждения админа).",
        is_builtin=True,
        follow_up_enabled=False,
        follow_up_delay_hours=2,
        decline_after_hours=48,
    ),
    dict(
        name="Точный подбор",
        description="Долгие сроки, отказ никогда не предлагается автоматически — только вручную.",
        is_builtin=True,
        follow_up_enabled=False,
        follow_up_delay_hours=48,
        decline_after_hours=None,
    ),
    dict(
        name="Массовый набор",
        description="Для потокового найма большого числа кандидатов одной вакансии.",
        is_builtin=True,
        follow_up_enabled=False,
        follow_up_delay_hours=4,
        decline_after_hours=72,
    ),
]


def _seed_hiring_strategies() -> None:
    """One-time seed of builtin Strategy presets. Idempotent — does nothing
    if any builtin strategies already exist."""
    from sqlalchemy import text
    with engine.connect() as conn:
        try:
            count = conn.execute(text("SELECT COUNT(*) FROM hiring_strategies WHERE is_builtin = 1")).scalar()
        except Exception:
            return
        if count:
            return
    with engine.begin() as conn:
        for s in _BUILTIN_STRATEGIES:
            conn.execute(text("""
                INSERT INTO hiring_strategies
                    (name, description, is_builtin, follow_up_enabled, follow_up_delay_hours, decline_after_hours,
                     follow_up_message_1, follow_up_message_2, hh_message_with_link, hh_message_no_link, away_message)
                VALUES
                    (:name, :description, :is_builtin, :follow_up_enabled, :follow_up_delay_hours, :decline_after_hours,
                     '', '', '', '', '')
            """), s)


def _migrate_recruitment_kb_and_strategy_defaults() -> None:
    """One-time recruitment-feature rollout migration:
    - assigns the "Стандартный отбор" builtin strategy to any vacancy that
      doesn't have a strategy yet (so existing vacancies keep working);
    - moves legacy free-text Vacancy.knowledge_base into a vacancy-scoped
      KnowledgeBaseEntry row (flagged ai_checked=False for admin review);
    - forces follow_up_enabled=False in config.json exactly once, regardless
      of any pre-existing value, per explicit safety requirement.
    Gated by a marker key in config.json so it only ever runs once.
    """
    from sqlalchemy import text
    try:
        from app.services.config_service import ConfigService
        cfg_service = ConfigService()
        cfg = cfg_service.load()
    except Exception:
        cfg = None

    if cfg is not None and cfg.get("strategy_feature_migrated_v1"):
        return

    with engine.begin() as conn:
        try:
            default_id = conn.execute(
                text("SELECT id FROM hiring_strategies WHERE is_builtin = 1 AND name = 'Стандартный отбор' LIMIT 1")
            ).scalar()
        except Exception:
            default_id = None

        if default_id:
            try:
                conn.execute(
                    text("UPDATE vacancies SET strategy_id = :sid WHERE strategy_id IS NULL"),
                    {"sid": default_id},
                )
            except Exception:
                pass

        try:
            rows = conn.execute(
                text("SELECT id, knowledge_base FROM vacancies WHERE knowledge_base IS NOT NULL AND knowledge_base != ''")
            ).fetchall()
            for vid, kb_text in rows:
                conn.execute(text("""
                    INSERT INTO knowledge_base_entries
                        (scope, vacancy_id, category, question, answer, ai_checked, ai_check_summary)
                    VALUES
                        ('vacancy', :vid, 'Перенесено автоматически', 'Старая база знаний вакансии', :answer, 0,
                         'Перенесено из старого текстового поля при обновлении системы — рекомендуем проверить и подтвердить через ИИ-проверку.')
                """), {"vid": vid, "answer": kb_text})
        except Exception:
            pass

    if cfg is not None:
        try:
            cfg["follow_up_enabled"] = False
            cfg["strategy_feature_migrated_v1"] = True
            cfg_service.save(cfg)
        except Exception:
            pass
