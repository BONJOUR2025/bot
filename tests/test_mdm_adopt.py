"""Восстановление телефонов после потери реестра 05.10.2026."""
from datetime import datetime, timedelta, timezone

import pytest

import app.services.mdm_service as ms
from app.data.mdm_repository import MdmRepository
from app.schemas.mdm import MdmCheckinRequest, MdmPolicy

TOKEN = "A" * 40 + "b-_"


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setattr(ms, "ADOPT_UNTIL", datetime.now(timezone.utc) + timedelta(hours=1))
    return ms.MdmService(repo=MdmRepository(str(tmp_path / "mdm_devices.json")))


def test_unknown_token_is_adopted_with_unknown_policy(service):
    device = service.adopt_unknown(TOKEN, MdmCheckinRequest(model="RMX3938", applied_policy_version=7))
    assert device["policy_unknown"] is True
    assert device["policy_version"] == 7
    assert service.find_by_token(TOKEN)["id"] == device["id"]
    # повторно не заводим
    assert service.adopt_unknown(TOKEN, MdmCheckinRequest()) is None


def test_saving_policy_resumes_management_with_newer_version(service):
    device = service.adopt_unknown(TOKEN, MdmCheckinRequest(applied_policy_version=7))
    updated = service.set_policy(device["id"], MdmPolicy())
    assert updated.policy_version == 8
    assert service.find_by_token(TOKEN).get("policy_unknown") is False


def test_no_adoption_after_window_or_for_junk_tokens(service, monkeypatch):
    assert service.adopt_unknown("short", MdmCheckinRequest()) is None
    assert service.adopt_unknown("!" * 43, MdmCheckinRequest()) is None
    monkeypatch.setattr(ms, "ADOPT_UNTIL", datetime.now(timezone.utc) - timedelta(seconds=1))
    assert service.adopt_unknown(TOKEN, MdmCheckinRequest()) is None
