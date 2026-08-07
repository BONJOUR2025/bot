from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String

from app.db.base_class import Base


class LlmUsageLog(Base):
    """One row per llm_client.chat() call that returned usage data — powers
    the live tokens/rubles spend view in Настройки → Автоматизация.

    cost_rub is only populated for providers that report per-request cost
    (currently: polza, see https://polza.ai/docs/osobennosti/usage.md);
    it stays NULL for anthropic rows, where only token totals are meaningful.
    """

    __tablename__ = "llm_usage_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    provider = Column(String, nullable=False)
    model = Column(String, nullable=False, default="")
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    cost_rub = Column(Float, nullable=True)
