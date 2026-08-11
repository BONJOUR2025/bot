"""Регрессия: опрос сообщений hh не должен зависеть от названий этапов.

Найдено в бою. `_check_hh_messages` отбирал кандидатов по
`Candidate.stage.in_({"отклик", "собеседование", "ждем"})` — списку из
старой воронки. После перехода на «5 этапов» новые кандидаты получают этап
«новый», которого в списке нет, и опрос замолчал полностью: 27 кандидатов
с запущенным опросом ждали ответа, а лог невинно писал «0 active candidates
to poll». У Авито это маскировали вебхук и отдельный путь опроса (он
фильтрует по состоянию quick_state, а не по этапу), у hh других путей нет —
поэтому там кандидатам буквально никто не отвечал.

Отбор теперь строится на состоянии переписки, а не на строке этапа, так что
следующее переименование этапов его не сломает. Тест фиксирует именно это
свойство, а не конкретные названия.
"""
from __future__ import annotations

import json

from app.services import quick_screening, recruitment_stages as rs, recruitment_sync


class _Candidate:
    def __init__(self, stage, state=None):
        self.stage = stage
        self.quick_state_json = json.dumps(state, ensure_ascii=False) if state else None


def _selected(candidates):
    """Отбор берётся из боевого кода, а не переписывается здесь.

    Раньше тут лежала копия условия — и ровно такая копия однажды уже дала
    зелёные тесты при сломанном проде: тест проверял свою версию логики,
    а не ту, что выполняется.
    """
    return [c for c in candidates if recruitment_sync.should_poll_messages(c)]


ASKING = {"status": "asking", "phase": "interest", "idx": 0, "answers": []}


class TestPollingIsStageNameIndependent:
    def test_candidate_on_the_current_default_stage_is_polled(self):
        """Ровно случай из боя: этап «новый», опрос идёт, ответа ждут."""
        c = _Candidate(rs.STAGE_NEW, ASKING)
        assert _selected([c]) == [c]

    def test_every_non_terminal_stage_with_a_running_screen_is_polled(self):
        cands = [_Candidate(s, ASKING) for s in
                 (rs.STAGE_NEW, rs.STAGE_SCREENING, rs.STAGE_ANSWERED, rs.STAGE_INTERVIEW)]
        assert _selected(cands) == cands

    def test_legacy_stage_names_still_work(self):
        """Кандидаты, доехавшие со старым этапом из бэкапа, не должны выпадать
        из опроса — отбор про переписку, а не про строку этапа."""
        c = _Candidate("отклик", ASKING)
        assert _selected([c]) == [c]

    def test_manual_conversation_without_a_screen_is_polled_too(self):
        """Опрос не запускался — входящее должно долетать как обычное
        уведомление админу, иначе кандидат снова остаётся без ответа."""
        c = _Candidate(rs.STAGE_NEW, None)
        assert _selected([c]) == [c]

    def test_finished_screens_are_polled(self):
        """Кандидат прошёл опрос до конца и лежит в «Ответил»/«Думает» — от
        него как раз и ждёшь «я согласен» после звонка.

        Раньше такие выпадали из опроса: код проверял только «опрос не
        запускался», хотя комментарий рядом обещал ещё и «завершён». Ответ
        такого кандидата не забирался вовсе, а по пути вебхука его глушил
        _route_to_quick_screening — сообщение исчезало целиком, без ответа и
        без уведомления. С этапом «Думает» это стало явной дырой.
        """
        for stage in (rs.STAGE_ANSWERED, rs.STAGE_THINKING):
            c = _Candidate(stage, {"status": "done"})
            assert _selected([c]) == [c]

    def test_intermediate_states_are_not_polled(self):
        """Ход не за кандидатом: опрос ждёт рабочих часов либо решения админа."""
        queued = _Candidate(rs.STAGE_NEW, {"status": "queued"})
        waiting = _Candidate(rs.STAGE_NEW, {"status": "waiting_admin"})
        assert _selected([queued, waiting]) == []
