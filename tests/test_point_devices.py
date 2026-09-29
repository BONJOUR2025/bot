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
