import json

import pytest

from app.data.mdm_repository import MdmRepository
from app.schemas.mdm import (
    MdmCheckinRequest,
    MdmCommandAck,
    MdmCommandCreate,
    MdmDeviceUpdate,
    MdmEnrollRequest,
    MdmKiosk,
    MdmPolicy,
    MdmRestrictions,
)
from app.services.mdm_service import MdmService, MdmValidationError


@pytest.fixture
def service(tmp_path):
    return MdmService(repo=MdmRepository(file_path=str(tmp_path / "mdm_devices.json")))


def enroll(service, device_id="androidid123"):
    return service.enroll(
        MdmEnrollRequest(
            device_id=device_id,
            model="Redmi Note 12",
            manufacturer="Xiaomi",
            android_version="13",
            agent_version="0.1.0",
            device_owner=True,
        )
    )


def test_enroll_creates_device_with_empty_policy(service):
    device, token = enroll(service)

    assert token
    assert device.id == "androidid123"
    assert device.policy_version == 1
    # Свежезарегистрированный телефон не должен ничего запрещать, пока оператор
    # не включит запреты руками.
    assert device.policy.restrictions.no_factory_reset is False
    assert device.policy.kiosk.enabled is False


def test_reenroll_keeps_device_but_rotates_token(service):
    _, first_token = enroll(service)
    device, second_token = enroll(service)

    assert first_token != second_token
    assert len(service.list_devices()) == 1
    assert service.find_by_token(first_token) is None
    assert service.find_by_token(second_token)["id"] == device.id


def test_set_policy_bumps_version(service):
    device, _ = enroll(service)
    policy = MdmPolicy(restrictions=MdmRestrictions(no_install_apps=True))

    updated = service.set_policy(device.id, policy)

    assert updated.policy_version == device.policy_version + 1
    assert updated.policy.restrictions.no_install_apps is True


def test_kiosk_without_packages_is_rejected(service):
    device, _ = enroll(service)
    policy = MdmPolicy(kiosk=MdmKiosk(enabled=True, packages=[]))

    with pytest.raises(MdmValidationError, match="kiosk_requires_packages"):
        service.set_policy(device.id, policy)


def test_install_apk_requires_https(service):
    device, _ = enroll(service)

    with pytest.raises(MdmValidationError, match="install_apk_requires_https_url"):
        service.queue_command(
            device.id,
            MdmCommandCreate(type="install_apk", params={"url": "http://example.com/a.apk"}),
        )


def test_uninstall_requires_package(service):
    device, _ = enroll(service)

    with pytest.raises(MdmValidationError, match="uninstall_requires_package"):
        service.queue_command(device.id, MdmCommandCreate(type="uninstall", params={}))


def test_pending_command_is_taken_once(service):
    device, _ = enroll(service)
    command = service.queue_command(device.id, MdmCommandCreate(type="lock"))

    first = service.take_pending_commands(device.id)
    second = service.take_pending_commands(device.id)

    assert [c["id"] for c in first] == [command["id"]]
    # Второй чек-ин не должен принести ту же команду снова — иначе телефон
    # выполнял бы её на каждом цикле.
    assert second == []


def test_ack_records_result(service):
    device, _ = enroll(service)
    command = service.queue_command(device.id, MdmCommandCreate(type="lock"))
    service.take_pending_commands(device.id)

    recorded = service.ack_commands(
        {"id": device.id},
        [MdmCommandAck(command_id=command["id"], status="done", result=None)],
    )

    assert recorded == 1
    stored = service.get_device(device.id).commands[-1]
    assert stored.status == "done"
    assert stored.acked_at


def test_applied_version_is_reported_after_policy_is_applied(service):
    device, _ = enroll(service)
    updated = service.set_policy(device.id, MdmPolicy(restrictions=MdmRestrictions(no_add_user=True)))

    # Чек-ин может назвать только предыдущую версию: политику агент получает
    # ответом на этот же запрос и применяет, когда тот уже ушёл.
    after_checkin = service.checkin({"id": device.id}, MdmCheckinRequest(applied_policy_version=1))
    assert after_checkin.applied_policy_version != updated.policy_version

    service.set_applied_version({"id": device.id}, updated.policy_version)

    assert service.get_device(device.id).applied_policy_version == updated.policy_version


def test_checkin_updates_state_and_keeps_previous_location(service):
    device, _ = enroll(service)
    service.checkin(
        {"id": device.id},
        MdmCheckinRequest(battery=80, latitude=59.93, longitude=30.31, location_at="2026-09-07T10:00:00Z"),
    )

    # Координаты снимаются только по команде locate, поэтому обычный чек-ин без
    # них не должен обнулять последнюю известную точку.
    after = service.checkin({"id": device.id}, MdmCheckinRequest(battery=75))

    assert after.battery == 75
    assert after.latitude == 59.93
    assert after.location_at == "2026-09-07T10:00:00Z"


def test_update_and_delete_device(service):
    device, _ = enroll(service)

    renamed = service.update_device(device.id, MdmDeviceUpdate(name="Ресепшен Озерки"))
    assert renamed.name == "Ресепшен Озерки"

    service.delete_device(device.id)
    assert service.list_devices() == []

    with pytest.raises(MdmValidationError, match="device_not_found"):
        service.get_device(device.id)


def test_command_poll_seconds_is_clamped(tmp_path, monkeypatch):
    from app.services import mdm_service

    monkeypatch.chdir(tmp_path)

    # Мусор в конфиге не должен молча превращаться в неуправляемый парк:
    # слишком частый опрос сажает батарею, слишком редкий убивает весь смысл.
    (tmp_path / "config.json").write_text('{"MDM_COMMAND_POLL_SECONDS": 1}', encoding="utf-8")
    assert mdm_service.current_command_poll_seconds() == 30

    (tmp_path / "config.json").write_text('{"MDM_COMMAND_POLL_SECONDS": 999999}', encoding="utf-8")
    assert mdm_service.current_command_poll_seconds() == 3600

    (tmp_path / "config.json").write_text('{"MDM_COMMAND_POLL_SECONDS": 300}', encoding="utf-8")
    assert mdm_service.current_command_poll_seconds() == 300

    # Нечитаемый конфиг — не повод падать: остаётся значение по умолчанию.
    (tmp_path / "config.json").write_text('{сломано', encoding="utf-8")
    assert mdm_service.current_command_poll_seconds() == 120


def test_token_is_never_exposed_in_device_schema(service):
    device, _ = enroll(service)

    assert not hasattr(device, "token")
    assert "token" not in service.get_device(device.id).model_dump()


# --- APK агента и провижининг ---------------------------------------------


def make_apk(version_name="0.3.0", version_code=7, package=b"pw.bonjour.mdm"):
    """Минимальный файл, похожий на APK ровно настолько, насколько проверяет сервис."""
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("AndroidManifest.xml", package.decode().encode("utf-16-le"))
        archive.writestr(
            "assets/agent_version.json",
            json.dumps({"version_name": version_name, "version_code": version_code}),
        )
    return buffer.getvalue()


def test_agent_info_without_apk(service, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert service.agent_info().available is False


def test_save_agent_apk_reads_version_from_inside(service, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    info = service.save_agent_apk(make_apk())

    assert info.available is True
    assert info.version_name == "0.3.0"
    assert info.version_code == 7
    assert info.sha256


def test_save_agent_apk_rejects_junk_and_foreign_packages(service, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(MdmValidationError, match="not_an_apk"):
        service.save_agent_apk(b"not a zip at all")

    # Чужой APK телефон и так не поставит поверх нашего — ключи не совпадут.
    # Ловим это здесь, чтобы «залил не тот файл» не уехало на весь парк.
    with pytest.raises(MdmValidationError, match="foreign_apk"):
        service.save_agent_apk(make_apk(package=b"com.example.other"))


def test_rollout_skips_devices_already_on_this_version(service, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    service.save_agent_apk(make_apk(version_name="0.3.0"))

    old, _ = service.enroll(MdmEnrollRequest(device_id="old-device", agent_version="0.2.1"))
    service.enroll(MdmEnrollRequest(device_id="current-device", agent_version="0.3.0"))

    result = service.rollout_agent_update()

    assert result.queued == 1
    assert result.skipped == 1
    queued = service.get_device(old.id).commands[-1]
    assert queued.type == "install_apk"
    assert queued.params["url"].endswith("/api/mdm/agent.apk")


def test_provisioning_reports_what_is_missing(service, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = service.provisioning()

    assert result.ready is False
    # Человеку нужно знать, чего именно не хватает, а не просто «нельзя».
    assert any("APK" in p for p in result.problems)
    assert any("MDM_ENROLL_KEY" in p for p in result.problems)


def test_provisioning_payload_carries_download_and_credentials(service, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    service.save_agent_apk(make_apk())
    (tmp_path / "config.json").write_text(
        json.dumps({"MDM_ENROLL_KEY": "k" * 16, "MDM_AGENT_SIGNATURE_CHECKSUM": "checksum"}),
        encoding="utf-8",
    )

    result = service.provisioning()

    assert result.ready is True
    payload = json.loads(result.payload)
    assert payload["android.app.extra.PROVISIONING_DEVICE_ADMIN_COMPONENT_NAME"] == (
        "pw.bonjour.mdm/pw.bonjour.mdm.AdminReceiver"
    )
    assert payload["android.app.extra.PROVISIONING_DEVICE_ADMIN_SIGNATURE_CHECKSUM"] == "checksum"
    # Ключ регистрации едет внутри QR: телефон должен зарегистрироваться сам,
    # без ввода чего-либо руками в салоне.
    assert payload["android.app.extra.PROVISIONING_ADMIN_EXTRAS_BUNDLE"]["enroll_key"] == "k" * 16
