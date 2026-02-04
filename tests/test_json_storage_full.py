"""Comprehensive tests for JsonStorage."""

import json
from pathlib import Path

from app.data.json_storage import JsonStorage


class TestJsonStorageInit:
    def test_creates_parent_directories(self, tmp_path):
        deep = tmp_path / "a" / "b" / "c" / "data.json"
        storage = JsonStorage(deep)
        assert deep.parent.exists()

    def test_accepts_string_path(self, tmp_path):
        storage = JsonStorage(str(tmp_path / "data.json"))
        assert isinstance(storage.path, Path)


class TestJsonStorageLoad:
    def test_load_returns_empty_dict_when_file_missing(self, tmp_path):
        storage = JsonStorage(tmp_path / "missing.json")
        assert storage.load() == {}

    def test_load_reads_existing_file(self, tmp_path):
        p = tmp_path / "data.json"
        p.write_text('{"a": 1}', encoding="utf-8")
        storage = JsonStorage(p)
        assert storage.load() == {"a": 1}

    def test_load_falls_back_to_example_when_empty(self, tmp_path):
        p = tmp_path / "data.json"
        p.write_text("{}", encoding="utf-8")
        example = tmp_path / "data.example.json"
        example.write_text('{"default": true}', encoding="utf-8")
        storage = JsonStorage(p)
        result = storage.load()
        assert result == {"default": True}

    def test_load_falls_back_to_example_when_missing(self, tmp_path):
        p = tmp_path / "data.json"
        example = tmp_path / "data.example.json"
        example.write_text('{"seeded": true}', encoding="utf-8")
        storage = JsonStorage(p)
        result = storage.load()
        assert result == {"seeded": True}
        assert p.exists(), "real file should be created from example"

    def test_load_handles_invalid_json(self, tmp_path):
        p = tmp_path / "data.json"
        p.write_text("not valid json", encoding="utf-8")
        storage = JsonStorage(p)
        result = storage.load()
        assert result == {}

    def test_load_unicode_content(self, tmp_path):
        p = tmp_path / "data.json"
        p.write_text('{"имя": "Иван"}', encoding="utf-8")
        storage = JsonStorage(p)
        assert storage.load() == {"имя": "Иван"}


class TestJsonStorageSave:
    def test_save_creates_file(self, tmp_path):
        p = tmp_path / "out.json"
        storage = JsonStorage(p)
        storage.save({"key": "value"})
        assert p.exists()
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data == {"key": "value"}

    def test_save_preserves_unicode(self, tmp_path):
        p = tmp_path / "out.json"
        storage = JsonStorage(p)
        storage.save({"название": "Тест"})
        raw = p.read_text(encoding="utf-8")
        assert "название" in raw
        assert "\\u" not in raw

    def test_save_overwrites_existing(self, tmp_path):
        p = tmp_path / "out.json"
        storage = JsonStorage(p)
        storage.save({"v": 1})
        storage.save({"v": 2})
        assert json.loads(p.read_text(encoding="utf-8")) == {"v": 2}

    def test_save_uses_indent(self, tmp_path):
        p = tmp_path / "out.json"
        storage = JsonStorage(p)
        storage.save({"a": 1})
        raw = p.read_text(encoding="utf-8")
        assert "\n" in raw  # indented output


class TestJsonStorageRoundTrip:
    def test_save_then_load(self, tmp_path):
        p = tmp_path / "data.json"
        storage = JsonStorage(p)
        original = {"employees": {"1": {"name": "Тест"}}}
        storage.save(original)
        loaded = storage.load()
        assert loaded == original
