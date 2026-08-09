from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String

from app.db.base_class import Base


class EmployeeLlmUsage(Base):
    """Per-employee LLM usage — for features where an individual employee
    (not just the account as a whole) needs to be attributed, e.g. the
    knowledge-base Q&A in the Telegram bot.

    This does NOT duplicate the account-wide spend view in
    llm_usage_service.get_usage_summary(), which pulls live from Polza's own
    GET /v1/history/generations and deliberately keeps no local copy — that
    endpoint already tracks everything billed to the key, better than a local
    mirror could. Employee identity is different: it is data Polza has no
    notion of at all (it only sees "a request happened"), so per-employee
    attribution can only ever come from a log we write ourselves, at the
    moment of the call.
    """

    __tablename__ = "employee_llm_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    employee_id = Column(String, nullable=False, index=True)
    # Denormalized on purpose: keeps old rows readable even if the employee's
    # name changes or the record is later archived/removed.
    employee_name = Column(String, nullable=False, default="")
    feature = Column(String, nullable=False, default="")  # e.g. "knowledge_base"
    provider = Column(String, nullable=False, default="")
    model = Column(String, nullable=False, default="")
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    # Only Polza reports cost per request; stays NULL for anthropic-provider
    # rows, where only token counts are meaningful (same convention as the
    # account-wide log had before it was replaced by the live Polza pull).
    cost_rub = Column(Float, nullable=True)
