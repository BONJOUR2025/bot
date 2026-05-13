from sqlalchemy import Boolean, Column, Integer, String, Text

from app.db.base_class import Base


class AdvanceRequest(Base):
    __tablename__ = "advance_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False, default="")
    phone = Column(String, nullable=False, default="")
    card_number = Column(String, nullable=False, default="")
    bank = Column(String, nullable=False, default="")
    amount = Column(Integer, nullable=False, default=0)
    method = Column(String, nullable=False, default="")
    payout_type = Column(String, nullable=True)
    status = Column(String, nullable=False, default="Ожидает", index=True)
    timestamp = Column(String, nullable=True)
    source_file = Column(String, nullable=True)
    note = Column(Text, nullable=False, default="")
    show_note_in_bot = Column(Boolean, nullable=False, default=False)
    force_notify_cashier = Column(Boolean, nullable=False, default=False)
    cash_move_id = Column(String, nullable=True, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "phone": self.phone,
            "card_number": self.card_number,
            "bank": self.bank,
            "amount": self.amount,
            "method": self.method,
            "payout_type": self.payout_type,
            "status": self.status,
            "timestamp": self.timestamp,
            "source_file": self.source_file,
            "note": self.note,
            "show_note_in_bot": self.show_note_in_bot,
            "force_notify_cashier": self.force_notify_cashier,
            "cash_move_id": self.cash_move_id,
        }
