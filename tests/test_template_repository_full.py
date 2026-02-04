"""Comprehensive tests for TemplateRepository."""

import json
from pathlib import Path

import pytest

from app.data.template_repository import TemplateRepository


def _make_repo(tmp_path, data=None):
    p = tmp_path / "templates.json"
    if data is None:
        data = [
            {"id": "1", "name": "Приветствие", "text": "Добро пожаловать!"},
            {"id": "2", "name": "Увольнение", "text": "Вы уволены."},
        ]
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return TemplateRepository(path=p)


class TestTemplateInit:
    def test_loads(self, tmp_path):
        repo = _make_repo(tmp_path)
        assert len(repo.list()) == 2

    def test_empty_file(self, tmp_path):
        p = tmp_path / "templates.json"
        p.write_text("[]", encoding="utf-8")
        repo = TemplateRepository(path=p)
        assert repo.list() == []

    def test_missing_file(self, tmp_path):
        p = tmp_path / "nonexistent.json"
        repo = TemplateRepository(path=p)
        assert repo.list() == []


class TestTemplateList:
    def test_list_returns_all(self, tmp_path):
        repo = _make_repo(tmp_path)
        result = repo.list()
        assert len(result) == 2
        assert result[0]["name"] == "Приветствие"


class TestTemplateCreate:
    def test_create_assigns_id(self, tmp_path):
        repo = _make_repo(tmp_path, data=[])
        created = repo.create("Тест", "Текст шаблона")
        assert "id" in created
        assert created["name"] == "Тест"
        assert created["text"] == "Текст шаблона"

    def test_create_appends(self, tmp_path):
        repo = _make_repo(tmp_path, data=[])
        repo.create("A", "Text A")
        repo.create("B", "Text B")
        assert len(repo.list()) == 2

    def test_create_auto_increments_id(self, tmp_path):
        repo = _make_repo(tmp_path, data=[])
        first = repo.create("A", "1")
        second = repo.create("B", "2")
        assert first["id"] != second["id"]

    def test_create_persists(self, tmp_path):
        p = tmp_path / "templates.json"
        p.write_text("[]", encoding="utf-8")
        repo = TemplateRepository(path=p)
        repo.create("Test", "Body")
        raw = json.loads(p.read_text(encoding="utf-8"))
        assert len(raw) == 1


class TestTemplateDelete:
    def test_delete_existing(self, tmp_path):
        repo = _make_repo(tmp_path)
        repo.delete("1")
        assert len(repo.list()) == 1

    def test_delete_nonexistent(self, tmp_path):
        repo = _make_repo(tmp_path)
        before = len(repo.list())
        repo.delete("999")
        assert len(repo.list()) == before

    def test_delete_persists(self, tmp_path):
        p = tmp_path / "templates.json"
        data = [{"id": "1", "name": "A", "text": "B"}]
        p.write_text(json.dumps(data), encoding="utf-8")
        repo = TemplateRepository(path=p)
        repo.delete("1")
        raw = json.loads(p.read_text(encoding="utf-8"))
        assert len(raw) == 0
