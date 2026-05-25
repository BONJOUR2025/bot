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
        ]:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # column already exists
