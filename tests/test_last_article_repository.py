"""Tests for LastArticleRepository (the колодка article/model number
registry) and LastRepository.rename_article (the cascade a rename needs)."""
import json

from app.data.last_article_repository import LastArticleRepository
from app.data.last_repository import LastRepository


def _article_repo(tmp_path, data=None):
    p = tmp_path / "last_articles.json"
    if data is not None:
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return LastArticleRepository(file_path=str(p))


def _last_repo(tmp_path, data=None):
    p = tmp_path / "lasts.json"
    if data is not None:
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return LastRepository(file_path=str(p))


def test_starts_empty_when_file_is_missing(tmp_path):
    repo = _article_repo(tmp_path)
    assert repo.list() == []


def test_create_and_list(tmp_path):
    repo = _article_repo(tmp_path)
    record = repo.create({"code": "4977", "name": "Классика", "note": "мужская"})
    assert record["code"] == "4977"
    assert record["name"] == "Классика"
    assert len(repo.list()) == 1


def test_code_is_stripped(tmp_path):
    repo = _article_repo(tmp_path)
    record = repo.create({"code": "  4977  "})
    assert record["code"] == "4977"


def test_get_by_code(tmp_path):
    repo = _article_repo(tmp_path)
    repo.create({"code": "4977"})
    repo.create({"code": "H1455"})
    found = repo.get_by_code("H1455")
    assert found is not None
    assert found["code"] == "H1455"
    assert repo.get_by_code("missing") is None


def test_update_renames_code_and_relabels(tmp_path):
    repo = _article_repo(tmp_path)
    record = repo.create({"code": "4977", "name": "old"})
    updated = repo.update(record["id"], {"code": "4977A", "name": "new", "note": "n"})
    assert updated["code"] == "4977A"
    assert updated["name"] == "new"
    assert repo.get(record["id"])["code"] == "4977A"


def test_update_nonexistent_returns_none(tmp_path):
    repo = _article_repo(tmp_path)
    assert repo.update("missing", {"code": "x"}) is None


def test_delete(tmp_path):
    repo = _article_repo(tmp_path)
    record = repo.create({"code": "4977"})
    removed = repo.delete(record["id"])
    assert removed["id"] == record["id"]
    assert repo.list() == []
    assert repo.delete(record["id"]) is None


def test_persists_across_reload(tmp_path):
    p = tmp_path / "last_articles.json"
    repo = LastArticleRepository(file_path=str(p))
    repo.create({"code": "4977"})
    reloaded = LastArticleRepository(file_path=str(p))
    assert len(reloaded.list()) == 1
    assert reloaded.list()[0]["code"] == "4977"


def _last(article, size="38.5", fullness="E", **kw):
    return {
        "id": f"id-{article}-{size}-{fullness}", "article": article, "size": size,
        "fullness": fullness, "model": "", "material": "", "note": "",
        "scan_file_url": "", "engine": "slice_v1", "side": None,
        "length_mm": None, "width_mm": None, "height_mm": None,
        "ball_girth_mm": None, "instep_girth_mm": None, "ball_line_mm": None,
        "heel_height_mm": None, "toe_spring_mm": None, "profile": [],
        "created_at": "2026-01-01T00:00:00",
        **kw,
    }


def test_rename_article_updates_every_matching_last(tmp_path):
    repo = _last_repo(tmp_path, data=[
        _last("4977", size="38.5"), _last("4977", size="39"), _last("H1455", size="43"),
    ])
    count = repo.rename_article("4977", "4977A")
    assert count == 2
    codes = [item["article"] for item in repo.list()]
    assert codes == ["4977A", "4977A", "H1455"]


def test_rename_article_persists(tmp_path):
    p = tmp_path / "lasts.json"
    json.dump([_last("4977")], open(p, "w", encoding="utf-8"), ensure_ascii=False)
    repo = LastRepository(file_path=str(p))
    repo.rename_article("4977", "4977A")
    reloaded = LastRepository(file_path=str(p))
    assert reloaded.list()[0]["article"] == "4977A"


def test_rename_article_is_a_noop_for_the_same_code(tmp_path):
    repo = _last_repo(tmp_path, data=[_last("4977")])
    assert repo.rename_article("4977", "4977") == 0


def test_rename_article_matches_nothing_returns_zero(tmp_path):
    repo = _last_repo(tmp_path, data=[_last("4977")])
    assert repo.rename_article("missing", "x") == 0
    assert repo.list()[0]["article"] == "4977"
