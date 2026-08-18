"""Regression tests for the config.json clobber bug.

A transient unreadable/half-written config used to be read as ``{}`` and then
saved back, wiping every key. These tests pin the hardened behaviour: a corrupt
file aborts writes instead of wiping, and writes are atomic with a backup.
"""

import json

import pytest

from app.services.config_service import ConfigCorruptError, ConfigService


def _corrupt(path):
    path.write_text('{"KEEP": "me", "OTHER": "va', encoding="utf-8")  # truncated JSON


def test_patch_over_corrupt_does_not_wipe(tmp_path):
    p = tmp_path / "config.json"
    _corrupt(p)
    before = p.read_text(encoding="utf-8")
    svc = ConfigService(path=p)
    with pytest.raises(ConfigCorruptError):
        svc.patch({"new_key": "x"})
    # The corrupt file is left exactly as-is — not replaced by a {new_key} stub.
    assert p.read_text(encoding="utf-8") == before


def test_load_strict_raises_on_corrupt(tmp_path):
    p = tmp_path / "config.json"
    _corrupt(p)
    with pytest.raises(ConfigCorruptError):
        ConfigService(path=p).load_strict()


def test_load_stays_tolerant_on_corrupt(tmp_path):
    p = tmp_path / "config.json"
    _corrupt(p)
    assert ConfigService(path=p).load() == {}  # read-only path unchanged


def test_save_empty_over_populated_refused(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"A": 1, "B": 2}), encoding="utf-8")
    svc = ConfigService(path=p)
    with pytest.raises(ConfigCorruptError):
        svc.save({})
    assert json.loads(p.read_text(encoding="utf-8")) == {"A": 1, "B": 2}
    # force=True is the explicit escape hatch.
    svc.save({}, force=True)
    assert json.loads(p.read_text(encoding="utf-8")) == {}


def test_save_backs_up_previous_valid(tmp_path):
    p = tmp_path / "config.json"
    svc = ConfigService(path=p)
    svc.save({"first": "1"})
    svc.patch({"second": "2"})
    bak = p.with_suffix(p.suffix + ".bak")
    assert bak.exists()
    assert json.loads(bak.read_text(encoding="utf-8")) == {"FIRST": "1"}
    assert ConfigService(path=p).load() == {"first": "1", "second": "2"}


def test_patch_over_valid_still_merges(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"EXISTING": "old"}), encoding="utf-8")
    svc = ConfigService(path=p)
    result = svc.patch({"new_key": "new_val"})
    assert result["existing"] == "old"
    assert result["new_key"] == "new_val"
