"""Tests for LastRepository.update -- editing an already-scanned last's
metadata (article/size/fullness/... ) without re-uploading its .stl."""
import json

from app.data.last_repository import LastRepository


def _last(article="4977", size="38.5", fullness="E", **kw):
    return {
        "id": "the-id", "article": article, "size": size, "fullness": fullness,
        "model": "", "material": "", "note": "", "scan_file_url": "", "engine": "slice_v1",
        "side": None, "length_mm": 250.0, "width_mm": 90.0, "height_mm": 60.0,
        "ball_girth_mm": 220.0, "instep_girth_mm": 230.0, "ball_line_mm": 170.0,
        "heel_height_mm": None, "toe_spring_mm": None, "profile": [{"y": 0, "z": 0}],
        "created_at": "2026-01-01T00:00:00",
        **kw,
    }


def _repo(tmp_path, data=None):
    p = tmp_path / "lasts.json"
    if data is not None:
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return LastRepository(file_path=str(p))


def test_update_changes_editable_fields(tmp_path):
    repo = _repo(tmp_path, data=[_last()])
    updated = repo.update("the-id", {
        "article": "4977A", "size": "39", "fullness": "F", "model": "classic",
        "material": "кожа", "note": "исправлено", "side": "left",
        "heel_height_mm": 12.5, "toe_spring_mm": 20.0,
    })
    assert updated["article"] == "4977A"
    assert updated["size"] == "39"
    assert updated["fullness"] == "F"
    assert updated["model"] == "classic"
    assert updated["material"] == "кожа"
    assert updated["note"] == "исправлено"
    assert updated["side"] == "left"
    assert updated["heel_height_mm"] == 12.5
    assert updated["toe_spring_mm"] == 20.0


def test_update_does_not_touch_measured_fields(tmp_path):
    """length_mm/ball_girth_mm/profile/scan_file_url come from parsing the
    .stl -- editing metadata must not be able to silently corrupt them."""
    repo = _repo(tmp_path, data=[_last()])
    repo.update("the-id", {"article": "renamed"})
    record = repo.get("the-id")
    assert record["length_mm"] == 250.0
    assert record["ball_girth_mm"] == 220.0
    assert record["profile"] == [{"y": 0, "z": 0}]
    assert record["scan_file_url"] == ""


def test_update_persists_across_reload(tmp_path):
    p = tmp_path / "lasts.json"
    json.dump([_last()], open(p, "w", encoding="utf-8"), ensure_ascii=False)
    repo = LastRepository(file_path=str(p))
    repo.update("the-id", {"note": "saved"})
    reloaded = LastRepository(file_path=str(p))
    assert reloaded.get("the-id")["note"] == "saved"


def test_update_nonexistent_returns_none(tmp_path):
    repo = _repo(tmp_path, data=[_last()])
    assert repo.update("missing", {"note": "x"}) is None
