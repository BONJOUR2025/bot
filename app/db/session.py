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
    """Create all tables that don't exist yet, then apply any pending column migrations."""
    Base.metadata.create_all(bind=engine)
    _migrate_columns()


def _migrate_columns() -> None:
    """Add columns introduced after initial schema creation."""
    with engine.connect() as conn:
        _add_column_if_missing(conn, "payment_schedules", "objects", "TEXT DEFAULT '[]'")


def _add_column_if_missing(conn, table: str, column: str, definition: str) -> None:
    from sqlalchemy import text, inspect
    inspector = inspect(conn)
    tables = inspector.get_table_names()
    if table not in tables:
        return
    cols = {c["name"] for c in inspector.get_columns(table)}
    if column not in cols:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
        conn.commit()
