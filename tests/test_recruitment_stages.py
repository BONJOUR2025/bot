"""Этапы найма и флаги состояния (app/services/recruitment_stages.py).

Смысл разделения на этап и флаги: кандидат одновременно бывает «в опросе на
2 из 4» и «молчит третьи сутки». Если бы это было одним полем, пришлось бы
выбрать что-то одно — а нужно и то, и другое, чтобы с одного взгляда понять,
кто ждёт ответа.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from app.services import recruitment_stages as rs


class TestDeriveStage:
    def test_no_state_is_new(self):
        assert rs.derive_stage(None, None) == rs.STAGE_NEW
        assert rs.derive_stage(rs.STAGE_NEW, {}) == rs.STAGE_NEW

    def test_asking_is_screening(self):
        assert rs.derive_stage(rs.STAGE_NEW, {"status": "asking"}) == rs.STAGE_SCREENING

    def test_done_is_answered(self):
        assert rs.derive_stage(rs.STAGE_SCREENING, {"status": "done"}) == rs.STAGE_ANSWERED

    def test_counter_question_keeps_candidate_in_screening(self):
        state = {"status": "waiting_admin", "reason": "question", "answers": [{"q": "a", "a": "b"}]}
        assert rs.derive_stage(rs.STAGE_SCREENING, state) == rs.STAGE_SCREENING

    def test_failed_first_message_stays_new(self):
        """Первый вопрос не ушёл — опрос не начинался, кандидат ещё новый."""
        state = {"status": "waiting_admin", "reason": "send_failed", "answers": []}
        assert rs.derive_stage(rs.STAGE_NEW, state) == rs.STAGE_NEW

    def test_send_failure_midway_stays_in_screening(self):
        state = {"status": "waiting_admin", "reason": "send_failed", "answers": [{"q": "a", "a": "b"}]}
        assert rs.derive_stage(rs.STAGE_SCREENING, state) == rs.STAGE_SCREENING

    def test_human_stages_are_never_overwritten_by_the_bot(self):
        """Кандидата позвали на собеседование — дописанный им ответ не должен
        утащить карточку обратно в «опрос»."""
        for stage in (rs.STAGE_INTERVIEW, rs.STAGE_HIRED, rs.STAGE_REJECTED):
            assert rs.derive_stage(stage, {"status": "asking"}) == stage
            assert rs.derive_stage(stage, {"status": "done"}) == stage


class TestStageNeverGoesBackwards:
    """Воронка движется только вперёд — в том числе когда этап поставлен руками.

    «Ответил» — этап ботовский, поэтому HUMAN_STAGES его не защищал, и
    карточка, перетащенная туда руками, возвращалась в «Опрос» на ближайшем
    обновлении страницы.
    """

    def test_manual_move_to_answered_survives_a_refresh(self):
        state = {"status": "waiting_admin", "reason": "question",
                 "answers": [{"q": "a", "a": "b"}]}
        assert rs.derive_stage(rs.STAGE_ANSWERED, state) == rs.STAGE_ANSWERED

    def test_manual_move_to_answered_survives_an_ongoing_screen(self):
        assert rs.derive_stage(rs.STAGE_ANSWERED, {"status": "asking"}) == rs.STAGE_ANSWERED

    def test_screening_is_not_pushed_back_to_new_by_a_delivery_failure(self):
        """Состояние сбросили, но карточка уже была в опросе."""
        state = {"status": "waiting_admin", "reason": "send_failed", "answers": []}
        assert rs.derive_stage(rs.STAGE_SCREENING, state) == rs.STAGE_SCREENING

    def test_the_bot_still_moves_a_card_forward(self):
        assert rs.derive_stage(rs.STAGE_NEW, {"status": "asking"}) == rs.STAGE_SCREENING
        assert rs.derive_stage(rs.STAGE_SCREENING, {"status": "done"}) == rs.STAGE_ANSWERED

    def test_unknown_legacy_stage_does_not_freeze_the_card(self):
        assert rs.derive_stage("общение", {"status": "asking"}) == rs.STAGE_SCREENING


class TestCompletedScreenIsAnswered:
    """Пройденный опрос — это «ответил», даже когда разговор у человека.

    Кандидат, ответивший на все вопросы и задавший свой в последней
    реплике, висел в «Опросе» вместе с теми, кто ещё не начинал отвечать.
    То, что ему надо ответить, несёт флаг, а не этап.
    """

    def test_completed_screen_handed_to_admin_is_answered(self):
        state = {"status": "waiting_admin", "reason": "question", "completed": True,
                 "answers": [{"q": "a", "a": "b"}, {"q": "c", "a": "d"}]}
        assert rs.derive_stage(rs.STAGE_SCREENING, state) == rs.STAGE_ANSWERED

    def test_it_still_asks_for_a_reply(self):
        state = {"status": "waiting_admin", "reason": "question", "completed": True,
                 "answers": [{"q": "a", "a": "b"}]}
        codes = [f["code"] for f in rs.flags(state)]
        assert rs.FLAG_NEEDS_REPLY in codes

    def test_an_unfinished_screen_stays_in_screening(self):
        state = {"status": "waiting_admin", "reason": "question",
                 "answers": [{"q": "a", "a": "b"}]}
        assert rs.derive_stage(rs.STAGE_SCREENING, state) == rs.STAGE_SCREENING


class TestProgress:
    def test_counts_answers_against_questions(self):
        state = {"answers": [{"q": "1", "a": "x"}, {"q": "2", "a": "y"}]}
        assert rs.progress(state, ["1", "2", "3", "4"]) == {"answered": 2, "total": 4}

    def test_empty_state(self):
        assert rs.progress(None, ["1"]) == {"answered": 0, "total": 1}
        assert rs.progress({}, None) == {"answered": 0, "total": 0}


class TestFlags:
    NOW = datetime(2026, 8, 10, 12, 0, 0)

    def test_counter_question_flags_needs_reply(self):
        f = rs.flags({"status": "waiting_admin", "reason": "question"}, now=self.NOW)
        assert [x["code"] for x in f] == [rs.FLAG_NEEDS_REPLY]

    def test_send_failure_flags_undelivered(self):
        f = rs.flags({"status": "waiting_admin", "reason": "send_failed"}, now=self.NOW)
        assert [x["code"] for x in f] == [rs.FLAG_UNDELIVERED]

    def test_waiting_admin_without_reason_defaults_to_needs_reply(self):
        """Состояния, записанные до появления reason, не должны выглядеть как
        техническая ошибка — по смыслу это ожидание ответа человека."""
        f = rs.flags({"status": "waiting_admin"}, now=self.NOW)
        assert [x["code"] for x in f] == [rs.FLAG_NEEDS_REPLY]

    def test_silence_under_24h_is_not_flagged(self):
        state = {"status": "asking", "asked_at": (self.NOW - timedelta(hours=23)).isoformat()}
        assert rs.flags(state, now=self.NOW) == []

    def test_silence_over_24h_is_flagged_with_days(self):
        state = {"status": "asking", "asked_at": (self.NOW - timedelta(days=3)).isoformat()}
        [flag] = rs.flags(state, now=self.NOW)
        assert flag["code"] == rs.FLAG_SILENT
        assert flag["days"] == 3
        assert "3" in flag["label"]

    def test_exactly_one_day_reads_naturally(self):
        state = {"status": "asking", "asked_at": (self.NOW - timedelta(hours=25)).isoformat()}
        [flag] = rs.flags(state, now=self.NOW)
        assert flag["label"] == "молчит сутки"

    def test_silence_is_not_reported_for_finished_screens(self):
        """Кандидат ответил на всё — он не «молчит», ждать от него нечего."""
        old = (self.NOW - timedelta(days=5)).isoformat()
        assert rs.flags({"status": "done", "asked_at": old}, now=self.NOW) == []

    def test_broken_asked_at_does_not_crash(self):
        assert rs.flags({"status": "asking", "asked_at": "не дата"}, now=self.NOW) == []

    def test_healthy_screen_has_no_flags(self):
        state = {"status": "asking", "asked_at": self.NOW.isoformat()}
        assert rs.flags(state, now=self.NOW) == []


class TestLegacyMigration:
    def test_telegram_funnel_stages_collapse_into_new(self):
        """Привязки к телеграму больше нет — эти кандидаты просто ждут опроса."""
        for old in ("отклик", "ждем", "ждем_привязки", "общение"):
            assert rs.LEGACY_STAGE_MAP[old] == rs.STAGE_NEW

    def test_outcome_stages_are_preserved(self):
        assert rs.LEGACY_STAGE_MAP["собеседование"] == rs.STAGE_INTERVIEW
        assert rs.LEGACY_STAGE_MAP["нанят"] == rs.STAGE_HIRED
        assert rs.LEGACY_STAGE_MAP["отказ"] == rs.STAGE_REJECTED

    def test_every_legacy_stage_maps_to_a_real_stage(self):
        assert set(rs.LEGACY_STAGE_MAP.values()) <= set(rs.STAGES)


class TestNoAnswerFlag:
    """Недозвон — состояние поверх этапа, как и «молчит».

    Кандидат остаётся в «Ответил» (он ведь действительно ответил), но
    карточка обязана показывать, что ему уже звонили и не застали — иначе
    после пятнадцатого звонка непонятно, кому набирали, а кому нет.
    """
    NOW = datetime(2026, 8, 10, 12, 0, 0)

    def test_no_attempts_no_flag(self):
        assert rs.flags({}, now=self.NOW, call_attempts=0) == []

    def test_single_attempt_reads_naturally(self):
        [flag] = rs.flags({}, now=self.NOW, call_attempts=1,
                          last_call_at=self.NOW - timedelta(minutes=10))
        assert flag["code"] == rs.FLAG_NO_ANSWER
        assert flag["label"] == "не дозвонился, только что"
        assert flag["escalate"] is False

    def test_repeat_attempts_are_counted(self):
        [flag] = rs.flags({}, now=self.NOW, call_attempts=2,
                          last_call_at=self.NOW - timedelta(hours=5))
        assert flag["label"] == "не дозвонился ×2, 5 ч назад"
        assert flag["attempts"] == 2

    def test_days_for_older_attempts(self):
        [flag] = rs.flags({}, now=self.NOW, call_attempts=2,
                          last_call_at=self.NOW - timedelta(days=3))
        assert flag["label"] == "не дозвонился ×2, 3 дн. назад"

    def test_third_attempt_escalates(self):
        """Звонить четвёртый раз бессмысленно — карточке пора требовать
        решения, а не выглядеть как «просто перезвонить»."""
        [flag] = rs.flags({}, now=self.NOW, call_attempts=rs.NO_ANSWER_ESCALATE_AT)
        assert flag["escalate"] is True

    def test_missing_timestamp_still_shows_the_count(self):
        [flag] = rs.flags({}, now=self.NOW, call_attempts=2, last_call_at=None)
        assert flag["label"] == "не дозвонился ×2"

    def test_coexists_with_screening_flags(self):
        """Кандидат может одновременно молчать в переписке и не брать трубку —
        оба факта нужны, схлопывать их в один нельзя."""
        state = {"status": "asking", "asked_at": (self.NOW - timedelta(days=2)).isoformat()}
        codes = [f["code"] for f in rs.flags(state, now=self.NOW, call_attempts=1)]
        assert codes == [rs.FLAG_NO_ANSWER, rs.FLAG_SILENT]


class TestReserve:
    """Резерв — отстойник для условно мёртвых: организаций, случайных чатов,
    откликов двухлетней давности.

    Именно перемещением, а не удалением: карточка остаётся ключом, по
    которому импорт узнаёт уже виденного человека. Удалённые возвращаются
    при следующей переподключённой интеграции — это уже происходило, когда
    объединение источников Авито разом вернуло 40 старых чатов.
    """

    def test_reserve_is_a_valid_stage(self):
        assert rs.STAGE_RESERVE in rs.STAGES

    def test_bot_never_moves_a_reserved_candidate(self):
        """Иначе входящее сообщение вытащило бы карточку обратно в воронку —
        ровно то, от чего резерв и заводили."""
        for state in ({"status": "asking"}, {"status": "done"}, {}, None):
            assert rs.derive_stage(rs.STAGE_RESERVE, state) == rs.STAGE_RESERVE

    def test_reserve_is_terminal(self):
        """Опрос сообщений отбирает кандидатов по TERMINAL_STAGES — резерв
        должен выпадать оттуда вместе с «нанят» и «отказ»."""
        assert rs.STAGE_RESERVE in rs.TERMINAL_STAGES
        assert rs.STAGE_HIRED in rs.TERMINAL_STAGES
        assert rs.STAGE_REJECTED in rs.TERMINAL_STAGES

    def test_working_stages_are_not_terminal(self):
        for stage in (rs.STAGE_NEW, rs.STAGE_SCREENING, rs.STAGE_ANSWERED,
                      rs.STAGE_THINKING, rs.STAGE_INTERVIEW):
            assert stage not in rs.TERMINAL_STAGES

    def test_reserve_is_not_a_rejection(self):
        """Разные вещи: отказ — решение по человеку, резерв — «это вообще не
        кандидат». Смешивать их значит портить статистику отказов."""
        assert rs.STAGE_RESERVE != rs.STAGE_REJECTED
