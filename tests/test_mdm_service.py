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

    with pytest.raises(MdmValidationError, match="kiosk_requires_app"):
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


def test_setting_poll_seconds_keeps_other_config_keys(service, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.json").write_text(
        json.dumps({"MDM_ENROLL_KEY": "k" * 16, "llm_provider": "polza"}), encoding="utf-8"
    )

    info = service.set_command_poll_seconds(300)

    assert info.command_poll_seconds == 300
    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    # Запись идёт через ConfigService именно ради этого: у config.json уже была
    # история, когда правка одного ключа сносила все остальные.
    assert saved["llm_provider"] == "polza"
    assert saved["MDM_ENROLL_KEY"] == "k" * 16


def test_poll_seconds_outside_bounds_is_rejected(service, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(MdmValidationError, match="poll_seconds_out_of_range"):
        service.set_command_poll_seconds(5)
    with pytest.raises(MdmValidationError, match="poll_seconds_out_of_range"):
        service.set_command_poll_seconds(99999)


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
    assert mdm_service.current_command_poll_seconds() == 600


def test_token_is_never_exposed_in_device_schema(service):
    device, _ = enroll(service)

    assert not hasattr(device, "token")
    assert "token" not in service.get_device(device.id).model_dump()


# --- APK агента и провижининг ---------------------------------------------


def make_axml(package="pw.bonjour.mdm", version_name="1.0", version_code=42):
    """Собирает настоящий бинарный AndroidManifest.xml.

    Не «что-нибудь похожее»: разбор AXML — единственное место, где мы читаем
    чужой двоичный формат по спецификации, и проверять его на подделке
    бессмысленно. Здесь ровно та раскладка чанков, что лежит в реальном APK.
    """
    import struct

    strings = ["package", "versionName", "versionCode", "manifest", package, version_name]

    # Пул строк: массив смещений, затем UTF-16 строки (длина, символы, ноль).
    blob = b""
    offsets = []
    for value in strings:
        offsets.append(len(blob))
        blob += struct.pack("<H", len(value)) + value.encode("utf-16-le") + bytes(2)
    blob += bytes(-len(blob) % 4)

    strings_start = 28 + 4 * len(strings)
    pool_size = strings_start + len(blob)
    pool = struct.pack(
        "<HHIIIIII", 0x0001, 28, pool_size, len(strings), 0, 0, strings_start, 0
    )
    pool += b"".join(struct.pack("<I", o) for o in offsets) + blob

    def attribute(name_index, raw_index, value_type, data):
        # ns, name, rawValue, затем размер значения, res0, тип и данные.
        return struct.pack(
            "<IIIHBBI", 0xFFFFFFFF, name_index, raw_index, 8, 0, value_type, data
        )

    attributes = (
        attribute(0, 4, 0x03, 4)           # package
        + attribute(1, 5, 0x03, 5)         # versionName
        + attribute(2, 0xFFFFFFFF, 0x10, version_code)
    )
    tag_size = 16 + 20 + len(attributes)
    tag = struct.pack(
        "<HHIIIIIHHHHHH",
        0x0102, 16, tag_size,
        1, 0xFFFFFFFF,      # номер строки, комментарий
        0xFFFFFFFF, 3,      # ns, name -> "manifest"
        20, 20, 3, 0, 0, 0,  # смещение/размер/количество атрибутов
    ) + attributes

    body = pool + tag
    return struct.pack("<HHI", 0x0003, 8, 8 + len(body)) + body


def make_apk(version_name="0.3.0", version_code=7, package="pw.bonjour.mdm"):
    """Минимальный файл, похожий на APK ровно настолько, насколько нужно сервису."""
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("AndroidManifest.xml", make_axml(package=package))
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
        service.save_agent_apk(make_apk(package="com.example.other"))


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


# --- инвентаризация и каталог приложений -----------------------------------


def test_apps_are_stored_only_when_sent(service):
    device, _ = enroll(service)

    service.checkin(
        {"id": device.id},
        MdmCheckinRequest(
            apps_hash="abc",
            apps=[{"package": "com.whatsapp", "label": "WhatsApp", "version_code": 5}],
        ),
    )
    # Список приезжает не каждый чек-ин, а только когда изменился: его
    # отсутствие означает «не менялся», а не «приложений больше нет».
    after = service.checkin({"id": device.id}, MdmCheckinRequest(apps_hash="abc"))

    assert [a.package for a in after.apps] == ["com.whatsapp"]
    assert after.apps_updated_at


def test_library_upload_reads_package_from_manifest(service, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    app = service.save_library_app("whatsapp.apk", make_apk(package="com.whatsapp"))

    assert app.filename == "whatsapp.apk"
    assert app.package == "com.whatsapp"
    assert app.url.endswith(app.id + ".apk")
    assert service.list_library()[0].id == app.id


def test_library_keeps_file_when_manifest_is_unreadable(service, tmp_path, monkeypatch):
    import io
    import zipfile

    monkeypatch.chdir(tmp_path)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("AndroidManifest.xml", b"not a real manifest")

    # Разобрать нечем — но файл всё равно должен лечь в каталог и ставиться:
    # установщик Android разберётся сам, имя пакета нужно только панели.
    app = service.save_library_app("exotic.apk", buffer.getvalue())

    assert app.package is None
    assert app.kind == "apk"
    assert app.filename == "exotic.apk"
    assert app.size > 0


def test_library_rejects_non_apk(service, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(MdmValidationError, match="not_an_apk"):
        service.save_library_app("readme.txt", b"just some text")


def test_install_from_library_queues_command_with_library_url(service, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    device, _ = enroll(service)
    app = service.save_library_app("app.apk", make_apk())

    command = service.install_library_app(device.id, app.id)

    assert command["type"] == "install_apk"
    assert command["params"]["url"] == app.url

    with pytest.raises(MdmValidationError, match="app_not_found"):
        service.install_library_app(device.id, "no-such-app")


def test_library_counts_where_package_is_installed(service, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = service.save_library_app("agent.apk", make_apk())

    first, _ = service.enroll(MdmEnrollRequest(device_id="phone-one"))
    service.enroll(MdmEnrollRequest(device_id="phone-two"))
    service.checkin(
        {"id": first.id},
        MdmCheckinRequest(apps_hash="h", apps=[{"package": "pw.bonjour.mdm"}]),
    )

    stored = service.list_library()[0]
    assert stored.package == "pw.bonjour.mdm"
    assert stored.installed_on == 1


def test_delete_library_app_removes_file(service, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = service.save_library_app("app.apk", make_apk())

    service.delete_library_app(app.id)

    assert service.list_library() == []
    with pytest.raises(MdmValidationError, match="app_not_found"):
        service.library_app_path(app.id)


def test_apk_info_never_raises_on_junk():
    from app.services.apk_info import read_apk_info

    # Разбор манифеста — «лучшее усилие»: чем угодно кормить можно, наружу
    # летят только None, иначе экзотический APK ломал бы загрузку файла.
    for junk in (b"", b"not a zip", make_apk()[:50]):
        assert read_apk_info(junk) == {
            "package": None,
            "version_name": None,
            "version_code": None,
        }


def test_apk_is_never_served_gzipped(tmp_path):
    """APK не должен проезжать через сжатие.

    В приложении включён GZipMiddleware, и он жал APK всем, кто прислал
    Accept-Encoding: gzip, — включая мастер первичной настройки Android. Тот
    пишет полученное в файл и сверяет подпись, у сжатого она не сходится, и
    провижининг по QR падал с «Can't set up device».
    """
    from fastapi import FastAPI
    from fastapi.responses import FileResponse
    from fastapi.testclient import TestClient
    from starlette.middleware.gzip import GZipMiddleware

    from app.api.mdm import _apk_response

    apk = tmp_path / "agent.apk"
    apk.write_bytes(b"PK" + bytes(200_000))

    app = FastAPI()
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    @app.get("/naive")
    def naive():
        return FileResponse(apk, media_type="application/vnd.android.package-archive")

    @app.get("/agent.apk")
    def agent():
        return _apk_response(apk, "agent.apk")

    client = TestClient(app)
    # Контрольный: без защиты middleware сжимает — значит проверка не холостая.
    assert client.get("/naive", headers={"Accept-Encoding": "gzip"}).headers.get(
        "content-encoding"
    ) == "gzip"
    assert client.get("/agent.apk", headers={"Accept-Encoding": "gzip"}).headers.get(
        "content-encoding"
    ) != "gzip"


def make_xapk(package="ru.agbis.AgbisPhoto", version_name="26.1.5", version_code=2615,
              with_obb=False):
    """Контейнер вроде XAPK: базовый APK, довески и описание от упаковщика."""
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(package + ".apk", make_axml(package, version_name, version_code))
        archive.writestr("config.arm64_v8a.apk", make_axml(package, version_name, version_code))
        archive.writestr("config.xxxhdpi.apk", make_axml(package, version_name, version_code))
        archive.writestr("manifest.json", json.dumps({
            "package_name": package,
            "version_name": version_name,
            "version_code": version_code,
            "split_apks": [{"file": package + ".apk", "id": "base"}],
        }))
        if with_obb:
            archive.writestr("Android/obb/" + package + "/main.1.obb", b"data")
    return buffer.getvalue()


def test_container_is_recognised_as_a_set_of_parts():
    from app.services.apk_info import read_package_info

    single = read_package_info(make_apk())
    assert single["kind"] == "apk"
    assert single["parts"] == 1

    bundle = read_package_info(make_xapk())
    assert bundle["kind"] == "xapk"
    assert bundle["package"] == "ru.agbis.AgbisPhoto"
    assert bundle["version_name"] == "26.1.5"
    assert bundle["version_code"] == 2615
    # Три вложенных APK: базовый и два довеска.
    assert bundle["parts"] == 3
    assert bundle["has_obb"] is False


def test_container_with_game_data_is_flagged():
    from app.services.apk_info import read_package_info

    # Данные для игр мы не раскладываем — приложение встанет, а игра без них
    # может не запуститься. Оператор должен об этом знать заранее.
    assert read_package_info(make_xapk(with_obb=True))["has_obb"] is True


def test_library_accepts_container_and_keeps_package_name(service, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    app = service.save_library_app("agbis.xapk", make_xapk())

    assert app.kind == "xapk"
    assert app.parts == 3
    assert app.package == "ru.agbis.AgbisPhoto"
    assert app.version_name == "26.1.5"


def test_library_still_rejects_files_that_are_not_packages(service, tmp_path, monkeypatch):
    import io
    import zipfile

    monkeypatch.chdir(tmp_path)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("readme.txt", b"no packages here")

    # Архив без единого APK внутри — не приложение, каким бы zip он ни был.
    with pytest.raises(MdmValidationError, match="not_an_apk"):
        service.save_library_app("random.zip", buffer.getvalue())


def test_upload_token_is_read_live_from_config(tmp_path, monkeypatch):
    from app.services import mdm_service

    monkeypatch.chdir(tmp_path)
    assert mdm_service.current_upload_token() == ""

    # Читается живьём, как и остальные ключи MDM: сменить токен сборки должно
    # быть можно без деплоя и перезапуска.
    (tmp_path / "config.json").write_text(
        json.dumps({"MDM_UPLOAD_TOKEN": "t" * 48}), encoding="utf-8"
    )
    assert mdm_service.current_upload_token() == "t" * 48


def test_agent_downgrade_is_refused(service, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    service.save_agent_apk(make_apk(version_name="0.2.8", version_code=11))

    # Android не поставит версию старее поверх новой: раскатка такого APK
    # означала бы, что весь парк отчитается ошибкой установки.
    with pytest.raises(MdmValidationError, match="agent_downgrade_11_to_7"):
        service.save_agent_apk(make_apk(version_name="0.2.4", version_code=7))

    assert service.agent_info().version_name == "0.2.8"

    # Более новая — принимается.
    service.save_agent_apk(make_apk(version_name="0.2.9", version_code=12))
    assert service.agent_info().version_code == 12


def test_snapshot_is_stored_and_served(service, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    device, _ = enroll(service)

    snapshot_id = service.save_snapshot({"id": device.id}, "back", bytes([255, 216]) + b"jpegbytes")

    card = service.get_device(device.id)
    assert len(card.snapshots) == 1
    assert card.snapshots[0].lens == "back"
    assert (snapshot_id + ".jpg?") in card.snapshots[0].url
    assert service.snapshot_path(device.id, snapshot_id).read_bytes() == bytes([255, 216]) + b"jpegbytes"


def test_only_last_snapshot_per_lens_is_kept(service, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    device, _ = enroll(service)

    # Держим по одному последнему кадру на камеру: новый снимок задней камеры
    # затирает прежний задний, но не трогает фронтальный.
    back1 = service.save_snapshot({"id": device.id}, "back", bytes([1]))
    front1 = service.save_snapshot({"id": device.id}, "front", bytes([2]))
    back2 = service.save_snapshot({"id": device.id}, "back", bytes([3]))

    card = service.get_device(device.id)
    kept = {s.lens: s.id for s in card.snapshots}
    assert kept == {"back": back2, "front": front1}

    # Файл затёртого заднего кадра удалён, фронтальный и новый задний живы.
    with pytest.raises(MdmValidationError, match="snapshot_not_found"):
        service.snapshot_path(device.id, back1)
    assert service.snapshot_path(device.id, back2).read_bytes() == bytes([3])
    assert service.snapshot_path(device.id, front1).read_bytes() == bytes([2])


def test_snapshot_path_rejects_traversal(service, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    device, _ = enroll(service)

    # id приходит из URL — в путь не должно попасть ничего, кроме hex.
    with pytest.raises(MdmValidationError, match="snapshot_not_found"):
        service.snapshot_path(device.id, "..%2f..%2fconfig")


def test_snapshot_url_is_signed_and_verifiable():
    import time
    from app.services.mdm_service import sign_snapshot, verify_snapshot_sig, snapshot_url

    url = snapshot_url("dev1", "snap1")
    # Ссылка — обычный https-адрес (открывается в браузере как скан паспорта),
    # но с подписью и сроком: без действительной подписи снимок не отдаётся.
    assert "/api/mdm/devices/dev1/snapshots/snap1.jpg?exp=" in url
    assert "&sig=" in url

    exp = int(time.time()) + 100
    sig = sign_snapshot("dev1", "snap1", exp)
    assert verify_snapshot_sig("dev1", "snap1", exp, sig) is True
    assert verify_snapshot_sig("dev1", "snap1", exp, "deadbeef") is False
    # Просроченная — отклоняется.
    past = int(time.time()) - 1
    assert verify_snapshot_sig("dev1", "snap1", past, sign_snapshot("dev1", "snap1", past)) is False
    # Подпись привязана к конкретному снимку: чужим id не воспользоваться.
    assert verify_snapshot_sig("dev1", "other", exp, sig) is False


def test_new_commands_validate_params(service):
    device, _ = enroll(service)

    with pytest.raises(MdmValidationError, match="clear_app_data_requires_package"):
        service.queue_command(device.id, MdmCommandCreate(type="clear_app_data", params={}))
    with pytest.raises(MdmValidationError, match="set_app_enabled_requires_package"):
        service.queue_command(device.id, MdmCommandCreate(type="set_app_enabled", params={}))

    # ring зажимается в разумные границы.
    cmd = service.queue_command(device.id, MdmCommandCreate(type="ring", params={"seconds": 99999}))
    assert cmd["params"]["seconds"] == 300
    # громкость зажимается в 0..100.
    cmd = service.queue_command(device.id, MdmCommandCreate(type="set_volume", params={"percent": 250}))
    assert cmd["params"]["percent"] == 100
    # set_app_enabled нормализует enabled в bool.
    cmd = service.queue_command(
        device.id, MdmCommandCreate(type="set_app_enabled", params={"package": "com.x", "enabled": 1})
    )
    assert cmd["params"]["enabled"] is True


def test_message_command_updates_lock_message_in_card(service):
    device, _ = enroll(service)

    service.queue_command(device.id, MdmCommandCreate(type="message", params={"text": "Верните телефон"}))
    assert service.get_device(device.id).lock_message == "Верните телефон"

    # Пустой текст снимает сообщение.
    service.queue_command(device.id, MdmCommandCreate(type="message", params={"text": ""}))
    assert service.get_device(device.id).lock_message is None


def test_checkin_stores_telemetry(service):
    device, _ = enroll(service)

    updated = service.checkin(
        {"id": device.id},
        MdmCheckinRequest(
            storage_total_mb=64000, storage_free_mb=32000, ram_total_mb=6000,
            network="wifi", wifi_ssid="Salon-WiFi", ip_address="192.168.1.5",
            uptime_seconds=3600, secure_lock=True,
        ),
    )

    assert updated.storage_free_mb == 32000
    assert updated.ram_total_mb == 6000
    assert updated.network == "wifi"
    assert updated.wifi_ssid == "Salon-WiFi"
    assert updated.ip_address == "192.168.1.5"
    assert updated.secure_lock is True

    # Пустой чек-ин не затирает уже собранную телеметрию.
    after = service.checkin({"id": device.id}, MdmCheckinRequest(battery=50))
    assert after.wifi_ssid == "Salon-WiFi"


def test_kiosk_requires_an_app(service):
    device, _ = enroll(service)
    from app.schemas.mdm import MdmKiosk
    policy = MdmPolicy(kiosk=MdmKiosk(enabled=True))
    with pytest.raises(MdmValidationError, match="kiosk_requires_app"):
        service.set_policy(device.id, policy)

    # С домашним приложением — проходит.
    ok = service.set_policy(device.id, MdmPolicy(kiosk=MdmKiosk(enabled=True, home="ru.agbis.AgbisPhoto")))
    assert ok.policy.kiosk.home == "ru.agbis.AgbisPhoto"


def test_new_utility_commands_validate(service):
    device, _ = enroll(service)

    with pytest.raises(MdmValidationError, match="launch_app_requires_package"):
        service.queue_command(device.id, MdmCommandCreate(type="launch_app", params={}))
    with pytest.raises(MdmValidationError, match="grant_permission_requires"):
        service.queue_command(device.id, MdmCommandCreate(type="grant_permission", params={"package": "com.x"}))
    with pytest.raises(MdmValidationError, match="set_time_zone_requires_zone"):
        service.queue_command(device.id, MdmCommandCreate(type="set_time_zone", params={}))

    cmd = service.queue_command(
        device.id,
        MdmCommandCreate(type="grant_permission",
                         params={"package": "ru.agbis.AgbisPhoto", "permission": "android.permission.CAMERA"}),
    )
    assert cmd["params"]["grant"] is True

    # kiosk_exit не требует параметров.
    assert service.queue_command(device.id, MdmCommandCreate(type="kiosk_exit"))["type"] == "kiosk_exit"


def test_wifi_and_terminal_commands_validate(service):
    device, _ = enroll(service)

    with pytest.raises(MdmValidationError, match="add_wifi_requires_ssid"):
        service.queue_command(device.id, MdmCommandCreate(type="add_wifi", params={}))
    with pytest.raises(MdmValidationError, match="set_time_requires_epoch_ms"):
        service.queue_command(device.id, MdmCommandCreate(type="set_time", params={}))

    cmd = service.queue_command(
        device.id, MdmCommandCreate(type="add_wifi", params={"ssid": "Salon", "password": "secret"})
    )
    assert cmd["params"]["ssid"] == "Salon"
    assert cmd["params"]["hidden"] is False

    assert service.queue_command(
        device.id, MdmCommandCreate(type="set_stay_awake", params={"enabled": 1})
    )["params"]["enabled"] is True


def test_broadcast_queues_to_all_or_salon(service):
    a, _ = service.enroll(MdmEnrollRequest(device_id="phone-a"))
    b, _ = service.enroll(MdmEnrollRequest(device_id="phone-b"))
    service.update_device(a.id, MdmDeviceUpdate(salon_id="s1"))
    service.update_device(b.id, MdmDeviceUpdate(salon_id="s2"))

    res = service.broadcast_command(MdmCommandCreate(type="lock"))
    assert res.queued == 2 and res.total == 2

    only_s1 = service.broadcast_command(MdmCommandCreate(type="lock"), salon_id="s1")
    assert only_s1.queued == 1 and only_s1.total == 1

    # Кривая команда не уезжает никому: валидация до постановки.
    with pytest.raises(MdmValidationError):
        service.broadcast_command(MdmCommandCreate(type="add_wifi", params={}))


def test_checkin_stores_hardware_inventory(service):
    device, _ = enroll(service)
    updated = service.checkin(
        {"id": device.id},
        MdmCheckinRequest(serial_number="ABC123", imei="356938035643809", sim_operator="MTS"),
    )
    assert updated.serial_number == "ABC123"
    assert updated.imei == "356938035643809"
    assert updated.sim_operator == "MTS"


def test_lost_mode_queues_the_sequence(service):
    device, _ = enroll(service)
    cmds = service.lost_mode(device.id, "Верните телефон")
    types = [c["type"] for c in cmds]
    assert types == ["lock", "message", "ring", "locate", "camera"]
    assert cmds[1]["params"]["text"] == "Верните телефон"


def test_schedules_add_validate_and_run(service, tmp_path, monkeypatch):
    from app.data.mdm_schedule_repository import MdmScheduleRepository
    from app.schemas.mdm import MdmScheduleCreate

    svc = MdmService(
        repo=MdmRepository(file_path=str(tmp_path / "d.json")),
        schedule_repo=MdmScheduleRepository(file_path=str(tmp_path / "s.json")),
    )
    dev, _ = svc.enroll(MdmEnrollRequest(device_id="phone-x"))

    with pytest.raises(MdmValidationError, match="schedule_bad_time"):
        svc.add_schedule(MdmScheduleCreate(time="99:99", command_type="reboot"))

    sched = svc.add_schedule(MdmScheduleCreate(time="04:30", command_type="reboot", target="all"))
    assert sched.id and sched.time == "04:30"
    assert len(svc.list_schedules()) == 1

    # Не время — не срабатывает.
    assert svc.run_due_schedules("04:29", "2026-09-09") == 0
    # Время — срабатывает, команда встаёт телефону.
    assert svc.run_due_schedules("04:30", "2026-09-09") == 1
    assert svc.get_device(dev.id).commands[-1].type == "reboot"
    # Тот же день второй раз — не повторяется.
    assert svc.run_due_schedules("04:30", "2026-09-09") == 0

    svc.delete_schedule(sched.id)
    assert svc.list_schedules() == []


def test_queue_marker_changes_when_command_queued(service):
    """Маркер очереди должен ловить постановку команды.

    На нём стоит весь длинный опрос: не заметив правку файла, ждущий запрос
    провисел бы полное удержание с командой, уже лежащей в очереди.
    """
    device, _ = enroll(service)
    before = service.queue_marker()

    service.queue_command(device.id, MdmCommandCreate(type="reboot"))

    assert service.queue_marker() != before


def test_mark_seen_updates_last_seen_without_touching_report(service):
    """Отметка живости не должна подменять собой отчёт.

    Длинный опрос приходит куда чаще чек-ина и доказывает, что телефон на
    связи, но телеметрию он не несёт — и не должен обнулять уже собранную.
    """
    device, _ = enroll(service)
    service.checkin(
        service._repo.get(device.id),
        MdmCheckinRequest(battery=77, agent_version="0.8.0"),
    )
    before = service.get_device(device.id)

    service.mark_seen(device.id)
    after = service.get_device(device.id)

    assert after.last_seen_at >= before.last_seen_at
    assert after.battery == 77
    assert after.agent_version == "0.8.0"


def test_long_poll_seconds_stays_within_bounds(monkeypatch, tmp_path):
    """Мусор в конфиге не должен превращаться в вечно висящий запрос."""
    from app.services import mdm_service as module

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.json").write_text(
        json.dumps({"MDM_LONG_POLL_SECONDS": 9999}), encoding="utf-8"
    )
    assert module.current_long_poll_seconds() == module.MAX_LONG_POLL_SECONDS

    (tmp_path / "config.json").write_text(
        json.dumps({"MDM_LONG_POLL_SECONDS": 0}), encoding="utf-8"
    )
    assert module.current_long_poll_seconds() == module.MIN_LONG_POLL_SECONDS


def test_cancel_command_only_while_pending(service):
    """Отменить можно только то, что ещё не ушло на телефон."""
    device, _ = enroll(service)
    cmd = service.queue_command(device.id, MdmCommandCreate(type="wipe"))

    updated = service.cancel_command(device.id, cmd["id"])
    assert updated.commands[-1].status == "canceled"

    # Повторная отмена уже отменённой — не проходит.
    with pytest.raises(MdmValidationError, match="command_not_cancelable"):
        service.cancel_command(device.id, cmd["id"])

    # Отправленную отменять поздно: телефон её уже выполняет.
    sent = service.queue_command(device.id, MdmCommandCreate(type="reboot"))
    service.take_pending_commands(device.id)
    with pytest.raises(MdmValidationError, match="command_not_cancelable"):
        service.cancel_command(device.id, sent["id"])


def test_broken_command_row_does_not_break_whole_device_list(service):
    """Одна повреждённая запись не должна ронять страницу MDM целиком.

    Файл правят несколько процессов, а однажды его пришлось править руками —
    и неизвестный статус команды уронил выдачу всех устройств разом. История
    команд не стоит потери доступа к парку.
    """
    device, _ = enroll(service)
    service.queue_command(device.id, MdmCommandCreate(type="reboot"))

    raw = service._repo.get(device.id)
    raw["commands"][-1]["status"] = "какая-то ерунда"
    service._repo.upsert(device.id, {"commands": raw["commands"]})

    assert len(service.list_devices()) == 1
    assert service.get_device(device.id).commands[-1].status == "failed"


def test_mark_seen_is_throttled(service):
    """Отметка «на связи» не должна переписывать файл на каждом переподключении.

    Телефон возвращается каждые 25 секунд, а запись переписывает файл целиком:
    на парке салонов это была бы непрерывная перезапись и столь же непрерывное
    пробуждение всех открытых панелей.
    """
    device, _ = enroll(service)

    service.mark_seen(device.id)
    first = service.get_device(device.id).last_seen_at
    marker = service.queue_marker()

    # Сразу следом — записи быть не должно.
    service.mark_seen(device.id)
    assert service.get_device(device.id).last_seen_at == first
    assert service.queue_marker() == marker

    # А устаревшую отметку обновляем.
    from datetime import datetime, timedelta, timezone as tz
    stale = (datetime.now(tz.utc) - timedelta(minutes=5)).isoformat()
    service._repo.upsert(device.id, {"last_seen_at": stale})
    service.mark_seen(device.id)
    assert service.get_device(device.id).last_seen_at != stale


def test_mark_seen_survives_unreadable_timestamp(service):
    """Мусор в отметке не должен молча выключать признак живости."""
    device, _ = enroll(service)
    service._repo.upsert(device.id, {"last_seen_at": "не дата"})

    service.mark_seen(device.id)

    assert service.get_device(device.id).last_seen_at != "не дата"


def test_found_mode_undoes_what_lost_mode_left_on(service):
    """Отбой должен снимать ровно то, что само не погаснет.

    Сигнал и сообщение на экране остаются висеть до отдельной команды —
    разбирать их по одной пришлось бы как раз в спешке. Блокировку экрана
    отбой не трогает: «разблокировать удалённо» сняло бы защиту с найденного
    телефона, ровно наоборот тому, зачем режим включали.
    """
    device, _ = enroll(service)
    service.lost_mode(device.id, "Верните в салон")
    assert service.get_device(device.id).lock_message == "Верните в салон"

    cmds = service.found_mode(device.id)

    assert [c["type"] for c in cmds] == ["stop_ring", "message"]
    assert cmds[1]["params"]["text"] == ""
    # Карточка не должна дальше показывать снятое сообщение.
    assert service.get_device(device.id).lock_message is None
    # Разблокировки среди команд нет и быть не должно.
    assert "unlock" not in [c["type"] for c in cmds]


def test_found_mode_requires_existing_device(service):
    with pytest.raises(MdmValidationError, match="device_not_found"):
        service.found_mode("нет-такого")


def test_alert_requires_text(service):
    """Пустое полноэкранное сообщение показывать нечего.

    В отличие от надписи под замком, где пустой текст — это законное «снять
    сообщение», здесь пустое окно ещё и невозможно закрыть, если снята кнопка.
    Убирают его отдельной командой stop_alert.
    """
    device, _ = enroll(service)

    with pytest.raises(MdmValidationError, match="alert_requires_text"):
        service.queue_command(device.id, MdmCommandCreate(type="alert", params={"text": "   "}))


def test_alert_normalises_params(service):
    device, _ = enroll(service)

    cmd = service.queue_command(device.id, MdmCommandCreate(
        type="alert", params={"text": "  Зайдите к управляющему  ", "title": " Важно "},
    ))

    assert cmd["params"]["text"] == "Зайдите к управляющему"
    assert cmd["params"]["title"] == "Важно"
    # По умолчанию сотрудник может закрыть окно: неснимаемое — осознанный выбор.
    assert cmd["params"]["dismissible"] is True


def test_alert_is_not_the_lock_screen_message(service):
    """alert не должен подменять надпись под замком в карточке.

    Это разные вещи: надпись висит под замком до отмены, окно показывается
    поверх работы. Если бы alert писался в lock_message, панель показывала бы
    на карточке то, чего на экране блокировки нет.
    """
    device, _ = enroll(service)

    service.queue_command(device.id, MdmCommandCreate(type="alert", params={"text": "Привет"}))

    assert service.get_device(device.id).lock_message is None


def test_stop_alert_needs_no_params(service):
    device, _ = enroll(service)
    cmd = service.queue_command(device.id, MdmCommandCreate(type="stop_alert"))
    assert cmd["type"] == "stop_alert"
