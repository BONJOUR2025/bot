"""One-time migration: read advance_requests.json → SQLite (hr.db).

Usage:
    cd /path/to/bot
    python -m scripts.migrate_json_to_db

The script is idempotent: records with IDs already present in the DB are skipped.
"""
from __future__ import annotations

import json
import os
import sys

# Ensure project root is on sys.path when run with `python -m scripts.migrate_json_to_db`
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.session import SessionLocal, init_db
from app.models.advance_request import AdvanceRequest
from app.data.payout_repository import normalize_status


JSON_FILE = os.environ.get("ADVANCE_REQUESTS_FILE", "advance_requests.json")


def migrate() -> None:
    if not os.path.exists(JSON_FILE):
        print(f"[migrate] File not found: {JSON_FILE}")
        return

    with open(JSON_FILE, encoding="utf-8") as f:
        records: list[dict] = json.load(f)

    print(f"[migrate] Read {len(records)} records from {JSON_FILE}")

    init_db()

    inserted = 0
    skipped = 0

    with SessionLocal() as db:
        existing_ids: set[int] = {
            row[0] for row in db.query(AdvanceRequest.id).all()
        }

        for rec in records:
            raw_id = rec.get("id")
            try:
                rec_id = int(raw_id) if raw_id is not None else None
            except (TypeError, ValueError):
                rec_id = None

            if rec_id is not None and rec_id in existing_ids:
                skipped += 1
                continue

            row = AdvanceRequest(
                user_id=str(rec.get("user_id", "")),
                name=rec.get("name", ""),
                phone=rec.get("phone", ""),
                card_number=rec.get("card_number", ""),
                bank=rec.get("bank", ""),
                amount=int(rec.get("amount", 0)),
                method=rec.get("method", ""),
                payout_type=rec.get("payout_type"),
                status=normalize_status(rec.get("status", "Ожидает")),
                timestamp=rec.get("timestamp"),
                source_file=rec.get("source_file"),
                note=rec.get("note", ""),
                show_note_in_bot=bool(rec.get("show_note_in_bot", False)),
                force_notify_cashier=bool(rec.get("force_notify_cashier", False)),
            )
            # Preserve original id if provided, so references from existing code stay valid
            if rec_id is not None:
                row.id = rec_id

            db.add(row)
            inserted += 1

        db.commit()

    print(f"[migrate] Done — inserted: {inserted}, skipped (already exist): {skipped}")
    if inserted > 0:
        print(f"[migrate] hr.db now contains the migrated records.")
        print(f"[migrate] You can keep advance_requests.json as a read-only backup.")


if __name__ == "__main__":
    migrate()
