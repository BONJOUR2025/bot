from types import SimpleNamespace

import pytest

from app.services import admin_help_service as svc


def _user(perms):
    return SimpleNamespace(id="u1", login="boss", display_name="Босс", permissions=perms)


def test_all_articles_parse_with_unique_ids():
    articles = svc.load_articles()
    assert len(articles) >= 40
    ids = [a.id for a in articles]
    assert len(ids) == len(set(ids))
    for a in articles:
        assert a.title and a.section and a.body
        assert a.route.startswith("/admin")


def test_salon_phones_and_computers_are_not_documented():
    for a in svc.load_articles():
        assert a.permission != "mdm"
        assert "mdm-devices" not in a.route and "workstations" not in a.route


def test_visibility_follows_permissions():
    only_payouts = {a.id for a in svc.visible_articles(["payouts"])}
    assert "payouts" in only_payouts
    assert "basics" in only_payouts            # общая статья — всем
    assert "payroll" not in only_payouts       # чужой раздел скрыт
    everything = svc.visible_articles(["*"])
    assert len(everything) == len(svc.load_articles())


def test_rate_limit(monkeypatch):
    monkeypatch.setattr(svc, "_rate", {})
    monkeypatch.setattr(svc, "RATE_LIMIT", 2)
    assert svc.check_rate("x") and svc.check_rate("x")
    assert not svc.check_rate("x")
    assert svc.check_rate("y")


@pytest.fixture
def fake_llm(monkeypatch):
    calls = []
    replies = []

    def chat(cfg, messages, **kw):
        calls.append({"messages": messages, **kw})
        return replies.pop(0)

    import app.services.llm_client as llm
    import app.services.config_service as cs

    monkeypatch.setattr(llm, "chat", chat)
    monkeypatch.setattr(llm, "get_client", lambda cfg: True)
    monkeypatch.setattr(cs.ConfigService, "load", lambda self: {"llm_provider": "polza"})
    return calls, replies


def test_offtopic_rejected_by_classifier_without_second_call(fake_llm):
    calls, replies = fake_llm
    replies.append("НЕТ")
    res = svc.ask("Сколько выручка сегодня?", [], _user(["*"]))
    assert res["offtopic"] is True
    assert res["answer"] == svc.OFFTOPIC_REPLY
    assert len(calls) == 1
    assert calls[0]["temperature"] == 0


def test_garbled_classifier_output_fails_closed(fake_llm):
    calls, replies = fake_llm
    replies.append("")
    assert svc.ask("Как одобрить выплату?", [], _user(["*"]))["offtopic"] is True


def test_on_topic_answer_with_refs(fake_llm):
    calls, replies = fake_llm
    replies += ["ДА", "1. Откройте «Выплаты».\n2. Нажмите «Одобрить».\nСм.: [payouts], [nonexistent]"]
    res = svc.ask("Как одобрить выплату?", [], _user(["payouts"]))
    assert res == {"answer": "1. Откройте «Выплаты».\n2. Нажмите «Одобрить».", "refs": ["payouts"], "offtopic": False}
    # Отвечающая модель видит только разрешённые статьи.
    system = calls[1]["system"]
    assert "[payouts]" in system and "[payroll]" not in system


def test_answer_model_marker_is_second_line_of_defence(fake_llm):
    calls, replies = fake_llm
    replies += ["ДА", "НЕ_ПО_ТЕМЕ"]
    assert svc.ask("Напиши стих про выплаты", [], _user(["*"]))["offtopic"] is True


def test_followup_uses_only_previous_user_questions(fake_llm):
    calls, replies = fake_llm
    replies += ["ДА", "Нажмите «Отменить».\nСм.: [sale-transfers]"]
    history = [
        {"role": "assistant", "content": "приветствие"},
        {"role": "user", "content": "Как перенести продажу?"},
        {"role": "assistant", "content": "Секретный ответ помощника"},
    ]
    svc.ask("а как отменить?", history, _user(["*"]))
    probe = calls[0]["messages"][0]["content"]
    assert "Как перенести продажу?" in probe and "Секретный ответ" not in probe
    # В основной вызов история идёт, начиная с реплики пользователя.
    assert calls[1]["messages"][0]["role"] == "user"


def test_every_article_says_where_it_lives_in_the_menu():
    """Путь «группа → пункт» должен совпадать с меню панели: иначе справка
    отправит человека искать пункт, которого нет."""
    import re
    from pathlib import Path

    nav = Path("admin_frontend/src/components/Navigation.jsx").read_text(encoding="utf-8")
    groups = {}
    for block in re.finditer(r"name: '([^']+)',\s*items: \[(.*?)\]", nav, flags=re.S):
        groups[block.group(1)] = set(re.findall(r"label: '([^']+)'", block.group(2)))
    for a in svc.load_articles():
        if a.id == "basics":
            continue
        assert a.menu, a.id
        group, item = [x.strip() for x in a.menu.split("→")]
        assert item in groups.get(group, set()), (a.id, a.menu)
