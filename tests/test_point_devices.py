from app.data.point_device_repository import PointCallRepository, PointDeviceRepository


def test_code_activates_once_and_token_resolves(tmp_path):
    repo = PointDeviceRepository(str(tmp_path / "devices.json"))
    code = repo.issue_code("salon-1", "admin")["code"]
    assert len(code) == 6
    token, device = repo.activate(code, "Стойка")
    assert device["salon_id"] == "salon-1"
    assert repo.activate(code, "ещё раз") is None          # код одноразовый
    assert repo.by_token(token)["id"] == device["id"]
    assert repo.by_token("чужой") is None
    assert "token_hash" not in repo.list("salon-1")[0]     # хэш наружу не отдаём
    assert repo.revoke(device["id"]) and repo.by_token(token) is None


def test_new_code_replaces_old_one(tmp_path):
    repo = PointDeviceRepository(str(tmp_path / "devices.json"))
    old = repo.issue_code("salon-1", "admin")["code"]
    new = repo.issue_code("salon-1", "admin")["code"]
    if old != new:
        assert repo.activate(old, "") is None
    assert repo.activate(new, "") is not None


def test_calls_keep_last(tmp_path):
    calls = PointCallRepository(str(tmp_path / "calls.json"))
    calls.add(10, "no_answer", "", "s", "d")
    calls.add(10, "reached", "придёт завтра", "s", "d")
    last = calls.last_for([10, 11])
    assert last[10]["result"] == "reached" and last[10]["count"] == 2 and 11 not in last


def test_handover_add_accept_and_scope(tmp_path):
    from app.data.point_device_repository import PointHandoverRepository

    repo = PointHandoverRepository(str(tmp_path / "h.json"))
    rec = repo.add("s1", "d1", by="Иванова", cash_counted="1 000", cash_agbis=1000.4,
                   checklist=["Касса пересчитана"], notes="  пакеты кончились ")
    assert rec["cash_counted"] is None  # строку с пробелом не угадываем — фронт шлёт число
    rec = repo.add("s1", "d1", by="Иванова", cash_counted=1000, cash_agbis=1000.4, checklist=[], notes="x")
    assert repo.list("s1")[0]["id"] == rec["id"]
    assert repo.list("s2") == []
    assert repo.accept("s2", rec["id"], by="Петрова", cash_counted=None, comment="") is None
    done = repo.accept("s1", rec["id"], by="Петрова", cash_counted=990, comment="нет 10 ₽")
    assert done["accepted"]["by"] == "Петрова" and done["accepted"]["cash_counted"] == 990
    again = repo.accept("s1", rec["id"], by="Сидорова", cash_counted=1, comment="")
    assert again["accepted"]["by"] == "Петрова"


def test_notes_lifecycle_and_scope(tmp_path):
    from app.data.point_device_repository import PointNoteRepository

    repo = PointNoteRepository(str(tmp_path / "n.json"))
    a = repo.add("s1", "d1", text="перезвонить", due="2026-10-01", by="Иванова",
                 order={"order_id": 5, "doc_num": "22585-8", "client": ""})
    repo.add("s1", "d1", text="пакеты", due="2026-10-09", by="", order=None)
    repo.add("s2", "d9", text="чужая", due="2026-10-01", by="", order=None)
    assert [n["text"] for n in repo.open_until("s1", "2026-10-02")] == ["перезвонить"]
    assert repo.update("s2", a["id"], done=True) is None
    moved = repo.update("s1", a["id"], due="2026-10-10")
    assert moved["due"] == "2026-10-10" and repo.open_until("s1", "2026-10-02") == []
    done = repo.update("s1", a["id"], done=True, by="Петрова")
    assert done["done"]["by"] == "Петрова"
    assert repo.update("s1", a["id"], done=False)["done"] is None
    assert repo.delete("s1", a["id"]) and not repo.delete("s1", a["id"])
    assert len(repo.list("s1")) == 1
