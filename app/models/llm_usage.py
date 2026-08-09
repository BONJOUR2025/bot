from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text

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
    # Part of prompt_tokens that the provider served from its prompt cache
    # instead of re-processing. The knowledge base is a large, unchanging
    # prefix, so on a cache-capable model this is nearly all of the prompt
    # and is billed at a fraction of the normal input rate — logging it is
    # the only way to tell "the cache is working" from "it silently isn't",
    # which is exactly what went wrong on the deepseek-chat route (Polza
    # fans out to third-party hosts with no prefix cache, so it reported
    # cached_tokens=0 on every single call).
    cached_tokens = Column(Integer, nullable=False, default=0)
    # Only Polza reports cost per request; stays NULL for anthropic-provider
    # rows, where only token counts are meaningful (same convention as the
    # account-wide log had before it was replaced by the live Polza pull).
    cost_rub = Column(Float, nullable=True)
    # What the employee actually asked and what the AI answered. Kept so a
    # costly row can be explained rather than just counted — a 50k-token
    # question looks identical to a cheap one in the numbers alone. Truncated
    # on write (see llm_usage_service.MAX_TEXT_CHARS): this is a spend-audit
    # trail, not a transcript store, and the system prompt (the actual bulk of
    # the tokens) is deliberately never copied in — it is the same knowledge
    # base every time and already lives in knowledge_documents.
    question = Column(Text, nullable=False, default="")
    answer = Column(Text, nullable=False, default="")
