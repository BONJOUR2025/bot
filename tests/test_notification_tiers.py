"""Уведомления делятся на три категории и читаются с одного взгляда.

За сутки приходило 34 уведомления из 19 разных мест, у каждого свой эмодзи
и формат. Проблема была не в количестве — 34 в сутки терпимо, — а в том,
что всё выглядело одинаково: «кандидат задал вопрос и ждёт» читалось тем же
весом, что «бот начал опрос». Глаз переставал различать, и терялось важное:
семерых кандидатов, ждавших ответа по двое суток, нашли не по уведомлениям,
а при сплошном чтении переписок.

Отсюда три категории с постоянным префиксом:
    🔴 НУЖЕН ОТВЕТ — человек ждёт вас прямо сейчас
    ⚪ (без префикса) — к сведению, бот справился сам
    🛠 СБОЙ — сломалась система, а не разговор с кандидатом
"""
from __future__ import annotations

import pathlib
import re

import pytest

APP = pathlib.Path(__file__).resolve().parent.parent / "app"

ACTION = "🔴 <b>НУЖЕН ОТВЕТ"
FAILURE = "🛠 <b>СБОЙ"
INFO = "⚪ <b>"


def _notification_texts() -> list[tuple[str, str]]:
    """(файл, первые символы текста) для каждого вызова send_notification."""
    out = []
    for path in APP.rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        for m in re.finditer(r'send_notification\(\s*\n?\s*f?"([^"]{0,60})', src):
            text = m.group(1)
            if "Тест уведомлений" in text:
                continue  # служебная проверка настроек, не часть ленты
            if text.strip("\\n ") == "":
                continue  # `"\n".join(lines)` — префикс лежит в первой строке списка
            out.append((path.name, text))
    return out


class TestEveryNotificationIsClassified:
    def test_all_have_a_tier_prefix(self):
        """Ни одно уведомление не должно быть «просто текстом»: без префикса
        оно снова смешается с остальными."""
        stray = [(f, t) for f, t in _notification_texts()
                 if not (t.startswith(ACTION) or t.startswith(FAILURE) or t.startswith(INFO))
                 # notify.py содержит сами шаблоны-помощники
                 and f != "notify.py"]
        assert stray == [], f"без категории: {stray}"

    def test_the_three_tiers_are_all_in_use(self):
        texts = [t for _, t in _notification_texts()]
        assert any(t.startswith(ACTION) for t in texts)
        assert any(t.startswith(FAILURE) for t in texts)
        assert any(t.startswith(INFO) for t in texts)


class TestNoiseIsGone:
    """Убрано то, что не требовало действия и приучало пролистывать ленту."""

    @pytest.mark.parametrize("phrase", [
        "Новый отклик — бот начал опрос",   # 6 в сутки, действия не требует
        "Кандидат больше не ищет работу",   # бот попрощался и закрыл сам
        "База знаний обновлена",            # тонуло среди сообщений кандидатов
        "TG не привязан 24ч",               # искало этап, которого больше нет
    ])
    def test_removed(self, phrase):
        hits = [f for f, t in _notification_texts() if phrase in t]
        assert hits == [], f"«{phrase}» всё ещё отправляется из {hits}"


class TestDeadCheckIsGone:
    def test_pending_tg_links_check_removed(self):
        """Проверка искала этап «ждем_привязки», которого в воронке нет с тех
        пор, как вырезали привязку к Telegram — то есть отрабатывала вхолостую
        на каждом цикле синхронизации и не могла сработать никогда."""
        src = (APP / "services" / "recruitment_sync.py").read_text(encoding="utf-8")
        # Проверяем отсутствие самой функции и её вызова. Строка
        # «ждем_привязки» осталась в поясняющем комментарии на её месте —
        # это как раз то, что стоит сохранить: следующий читатель не станет
        # искать пропавшую проверку.
        assert "async def _check_pending_tg_links" not in src
        assert "await _check_pending_tg_links" not in src


class TestHelpers:
    def test_prefixes_are_applied(self):
        from app.services import notify
        import inspect

        for fn, prefix in ((notify.notify_action, ACTION),
                           (notify.notify_failure, FAILURE)):
            assert prefix.split("<b>")[0].strip() in inspect.getsource(fn)
