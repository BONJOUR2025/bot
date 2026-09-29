"""Деление услуги между мастерами: наложение на отчёт, сводка, заработок."""
import pytest

from app.services import service_split_service as ss


def _svc(sid, out_uid, out_name, kredit, salary, warnings=None):
    return {"service_id": sid, "out_user_id": out_uid, "out_description": out_name,
            "kredit": kredit, "master_salary": salary, "warnings": warnings or []}


SPLITS = {
    1: {"parts": [{"user_id": 10, "name": "Иванов Иван", "agbis_name": "Иванов И.", "share": 0.6, "percent": 60},
                  {"user_id": 20, "name": "Петров Пётр", "agbis_name": "Петров П.", "share": 0.4, "percent": 40}],
        "by": "Старший"},
}


def test_apply_marks_only_split_services():
    services = [_svc(1, 10, "Иванов И.", 1000, 200), _svc(2, 20, "Петров П.", 500, 100)]
    out = ss.apply(services, SPLITS)
    assert [p["salary"] for p in out[0]["split"]] == [120.0, 80.0]
    assert [p["kredit"] for p in out[0]["split"]] == [600.0, 400.0]
    assert "split" not in out[1]
    assert "split" not in services[0]  # исходный кэш не портим


def test_rebuild_summary_moves_share_to_second_master(monkeypatch):
    services = ss.apply([_svc(1, 10, "Иванов И.", 1000, 200), _svc(2, 20, "Петров П.", 500, 100)], SPLITS)
    old = [{"master": "Иванов И.", "advances_since_last_salary": 50},
           {"master": "Петров П.", "advances_since_last_salary": 0}]
    summary = {r["master"]: r for r in ss._rebuild_summary(services, old)}
    assert summary["Иванов И."]["total_salary"] == 120.0
    assert summary["Петров П."]["total_salary"] == 180.0
    assert summary["Петров П."]["services_done"] == 2
    assert summary["Иванов И."]["to_pay"] == 70.0
    assert sum(r["total_salary"] for r in summary.values()) == 300.0


def test_salary_parts_without_out_is_empty():
    assert ss.salary_parts(_svc(3, 10, "Иванов И.", 1000, None)) == []


def test_validate_parts(monkeypatch):
    monkeypatch.setattr(ss, "agbis_names", lambda: {10: "Иванов И.", 20: "Петров П."})
    masters = {10: {"name": "Иванов Иван"}, 20: {"name": "Петров Пётр"}}
    ok = ss.validate_parts([{"master_uid": 10, "percent": 70}, {"master_uid": 20, "percent": 30}], masters)
    assert ok[0]["agbis_name"] == "Иванов И." and ok[1]["share"] == 0.3
    for bad, msg in [
        ([{"master_uid": 10, "percent": 100}], "2–5"),
        ([{"master_uid": 10, "percent": 50}, {"master_uid": 10, "percent": 50}], "дважды"),
        ([{"master_uid": 10, "percent": 50}, {"master_uid": 99, "percent": 50}], "списка"),
        ([{"master_uid": 10, "percent": 60}, {"master_uid": 20, "percent": 30}], "100%"),
        ([{"master_uid": 10, "percent": 100}, {"master_uid": 20, "percent": 0}], "больше нуля"),
    ]:
        with pytest.raises(ValueError, match=msg):
            ss.validate_parts(bad, masters)


def test_master_earned_includes_share_not_out_master():
    from app.services import master_bot_service as mbs

    services = ss.apply([_svc(1, 10, "Иванов И.", 1000, 200), _svc(2, 20, "Петров П.", 500, 100)], SPLITS)
    petrov = mbs.Master(employee_id="p", name="Петров", agbis_user_id=20, position="Мастер по ремонту")
    earned = mbs._earned(services, petrov)
    assert sorted(e["master_salary"] for e in earned) == [80.0, 100.0]
    ivanov = mbs.Master(employee_id="i", name="Иванов", agbis_user_id=10, position="Мастер по ремонту")
    assert [e["master_salary"] for e in mbs._earned(services, ivanov)] == [120.0]
