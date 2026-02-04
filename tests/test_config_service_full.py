"""Comprehensive tests for ConfigService."""

import json
from pathlib import Path

import pytest

from app.services.config_service import ConfigService
from tests.conftest import run_async


def _make_service(tmp_path, data=None):
    p = tmp_path / "config.json"
    if data is not None:
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return ConfigService(path=p)


class TestConfigServiceLoad:
    def test_load_empty(self, tmp_path):
        svc = _make_service(tmp_path)
        assert svc.load() == {}

    def test_load_existing(self, tmp_path):
        svc = _make_service(tmp_path, data={"KEY": "value"})
        result = svc.load()
        assert result["key"] == "value"

    def test_load_normalizes_keys_to_lower(self, tmp_path):
        svc = _make_service(tmp_path, data={"MY_KEY": "test"})
        result = svc.load()
        assert "my_key" in result

    def test_load_invalid_json_returns_empty(self, tmp_path):
        p = tmp_path / "config.json"
        p.write_text("invalid json", encoding="utf-8")
        svc = ConfigService(path=p)
        assert svc.load() == {}

    def test_load_non_dict_returns_empty(self, tmp_path):
        p = tmp_path / "config.json"
        p.write_text("[1, 2, 3]", encoding="utf-8")
        svc = ConfigService(path=p)
        assert svc.load() == {}


class TestConfigServiceSave:
    def test_save(self, tmp_path):
        svc = _make_service(tmp_path)
        result = svc.save({"key": "value"})
        assert "key" in result

    def test_save_normalizes_keys_to_upper(self, tmp_path):
        p = tmp_path / "config.json"
        svc = ConfigService(path=p)
        svc.save({"my_key": "test"})
        raw = json.loads(p.read_text(encoding="utf-8"))
        assert "MY_KEY" in raw

    def test_save_already_prepared(self, tmp_path):
        svc = _make_service(tmp_path)
        result = svc.save({"RAW_KEY": "value"}, already_prepared=True)
        assert "raw_key" in result


class TestConfigServicePatch:
    def test_patch(self, tmp_path):
        svc = _make_service(tmp_path, data={"EXISTING": "old"})
        result = svc.patch({"new_key": "new_val"})
        assert "existing" in result
        assert "new_key" in result

    def test_patch_overwrites(self, tmp_path):
        svc = _make_service(tmp_path, data={"KEY": "old"})
        result = svc.patch({"key": "new"})
        assert result["key"] == "new"


class TestConfigServiceUpload:
    def test_upload_valid_json(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            data = json.dumps({"uploaded_key": "test"}).encode("utf-8")
            await svc.upload(data)
            result = svc.load()
            assert "uploaded_key" in result
        run_async(_run())

    def test_upload_invalid_json_raises(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            with pytest.raises(ValueError, match="Invalid JSON"):
                await svc.upload(b"not json")
        run_async(_run())

    def test_upload_non_dict_saves_empty(self, tmp_path):
        svc = _make_service(tmp_path)
        async def _run():
            await svc.upload(json.dumps([1, 2]).encode("utf-8"))
            result = svc.load()
            assert result == {}
        run_async(_run())


class TestConfigServiceNormalization:
    def test_normalize_for_response(self):
        result = ConfigService._normalize_for_response({"KEY": "val", "Other": "x"})
        assert "key" in result
        assert "other" in result

    def test_prepare_for_storage(self):
        result = ConfigService._prepare_for_storage({"key": "val", "other": "x"})
        assert "KEY" in result
        assert "OTHER" in result

    def test_prepare_skips_non_string_keys(self):
        result = ConfigService._prepare_for_storage({123: "val", "key": "x"})
        assert 123 not in result
        assert "KEY" in result
