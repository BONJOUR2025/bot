"""Add cash_move_id column to advance_requests table."""
import sqlite3
from pathlib import Path

DB_PATH = Path("hr.db")

if not DB_PATH.exists():
    print("hr.db not found — nothing to migrate")
    raise SystemExit(0)

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cols = [row[1] for row in cur.execute("PRAGMA table_info(advance_requests)")]
if "cash_move_id" in cols:
    print("Column cash_move_id already exists — skipping")
else:
    cur.execute("ALTER TABLE advance_requests ADD COLUMN cash_move_id TEXT")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_advance_requests_cash_move_id ON advance_requests(cash_move_id)")
    conn.commit()
    print("Added cash_move_id column and index to advance_requests")

conn.close()
