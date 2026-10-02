"""Раздел «Помощь»: инструкции по панели и вопросы помощнику.

Под правом «help»: пока раздел обкатывается, он открыт только владельцу
(у него «*»), остальным выдаётся галочкой в «Настройки → Доступ». Какие
статьи видно, дополнительно решает admin_help_service по правам пользователя.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.services import admin_help_service as help_service
from app.services.access_control_service import ResolvedUser

from .dependencies import require_permission

log = logging.getLogger(__name__)


class HistoryItem(BaseModel):
    role: str
    content: str


class AskIn(BaseModel):
    question: str
    history: list[HistoryItem] = []


def create_help_router() -> APIRouter:
    router = APIRouter(prefix="/help", tags=["help"])

    @router.get("/articles")
    def articles(user: ResolvedUser = Depends(require_permission("help"))):
        return [a.public() for a in help_service.visible_articles(user.permissions)]

    @router.post("/ask")
    async def ask(data: AskIn, user: ResolvedUser = Depends(require_permission("help"))):
        question = (data.question or "").strip()
        if len(question) < 3:
            raise HTTPException(400, "Задайте вопрос подробнее.")
        if len(question) > help_service.MAX_QUESTION_LEN:
            raise HTTPException(400, f"Слишком длинный вопрос — уложитесь в {help_service.MAX_QUESTION_LEN} символов.")
        if not help_service.check_rate(user.id or user.login):
            raise HTTPException(429, "Слишком много вопросов подряд. Попробуйте через час или найдите ответ в инструкциях ниже.")
        try:
            return await asyncio.to_thread(
                help_service.ask, question, [h.model_dump() for h in data.history], user,
            )
        except Exception as exc:
            log.warning("Помощник по панели: %s", exc)
            text = str(exc)
            if "402" in text or "INSUFFICIENT_BALANCE" in text:
                raise HTTPException(503, "Закончился баланс нейросети — сообщите руководителю. Инструкции ниже доступны.")
            if text == "no_llm_key":
                raise HTTPException(503, "Помощник не настроен: нет ключа нейросети. Инструкции ниже доступны.")
            raise HTTPException(503, "Помощник сейчас недоступен. Посмотрите ответ в инструкциях ниже.")

    return router
