"""Реестр телефонов не должен теряться при параллельных запросах (инцидент 05.10.2026)."""
import json
import threading

import pytest

from app.data.mdm_repository import MdmRepository


def test_parallel_checkins_never_wipe_registry(tmp_path):
    path = tmp_path / "mdm_devices.json"
    repo = MdmRepository(str(path))
    for i in range(5):
        repo.upsert(f"dev{i}", {"token": f"t{i}", "n": 0})

    errors: list[Exception] = []

    def writer(i: int) -> None:
        try:
            for n in range(40):
                repo.upsert(f"dev{i}", {"n": n})
        except Exception as exc:  # pragma: no cover — сам факт ошибки и есть провал
            errors.append(exc)

    def reader() -> None:
        try:
            for _ in range(200):
                assert len(repo.list()) == 5
                assert repo.get_by_token("t3") is not None
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(5)]
    threads += [threading.Thread(target=reader) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    data = json.loads(path.read_text(encoding="utf-8"))
    assert sorted(d["id"] for d in data) == [f"dev{i}" for i in range(5)]
    assert all(d["n"] == 39 for d in data)


def test_unreadable_file_is_an_error_not_an_empty_registry(tmp_path):
    path = tmp_path / "mdm_devices.json"
    path.write_text('[{"id": "dev1", "tok', encoding="utf-8")
    repo = MdmRepository(str(path))
    with pytest.raises(RuntimeError):
        repo.upsert("dev2", {"token": "x"})
    # битый файл не перезаписан пустотой
    assert path.read_text(encoding="utf-8") == '[{"id": "dev1", "tok'


def test_previous_version_kept_as_backup(tmp_path):
    path = tmp_path / "mdm_devices.json"
    repo = MdmRepository(str(path))
    repo.upsert("dev1", {"token": "a"})
    repo.upsert("dev2", {"token": "b"})
    backup = json.loads((tmp_path / "mdm_devices.json.bak").read_text(encoding="utf-8"))
    assert [d["id"] for d in backup] == ["dev1"]
