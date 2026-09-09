"""Логика MDM: регистрация телефонов, политика, очередь команд.

Общий контур — в docs/mdm_overview.md. Коротко: агент на телефоне сам применяет
политику и сам следит за её актуальностью, сервер только хранит желаемое
состояние и очередь команд. Поэтому здесь нет ничего, что «идёт на телефон», —
только чтение и запись состояния.
"""

from __future__ import annotations

import hashlib
import io
import json
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.config import MDM_AGENT_APK_FILE, MDM_APPS_DIR
from app.data.mdm_repository import MdmRepository, get_mdm_repository
from app.data.mdm_schedule_repository import MdmScheduleRepository, get_mdm_schedule_repository
from app.schemas.mdm import (
    MdmAgentInfo,
    MdmAgentRolloutResult,
    MdmLibraryApp,
    MdmProvisioning,
    MdmSchedule,
    MdmScheduleCreate,
    MdmCheckinRequest,
    MdmCommandAck,
    MdmCommandCreate,
    MdmDevice,
    MdmDeviceUpdate,
    MdmEnrollRequest,
    MdmEnrollmentInfo,
    MdmPolicy,
)
from app.services.apk_info import read_apk_info, read_package_info
from app.settings import settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_enroll_key() -> str:
    """Ключ первичной регистрации, свежим чтением из config.json.

    Тот же приём, что у счётчиков посетителей (app/api/visitor_counters.py):
    ключ, сохранённый через админку, должен начать действовать сразу, без
    перезапуска процесса.
    """
    try:
        data = json.loads(Path("config.json").read_text(encoding="utf-8"))
        if key := data.get("MDM_ENROLL_KEY"):
            return str(key)
    except Exception:
        pass
    return settings.mdm_enroll_key


# Границы интервала опроса команд. Чаще получаса телефон заметно ест
# батарею, реже часа — теряется смысл будильника, ради которого всё это
# затевалось. Знают их и схема запроса, и подсказка в панели.
MIN_POLL_SECONDS = 30
MAX_POLL_SECONDS = 3600


def current_command_poll_seconds() -> int:
    """Интервал опроса команд, свежим чтением из config.json.

    Границы жёсткие: чаще 30 секунд телефон начнёт заметно есть батарею, реже
    часа — теряется весь смысл будильника. Мусор в конфиге не должен молча
    превращаться в неуправляемый парк.
    """
    value = settings.mdm_command_poll_seconds
    try:
        data = json.loads(Path("config.json").read_text(encoding="utf-8"))
        if (raw := data.get("MDM_COMMAND_POLL_SECONDS")) is not None:
            value = int(raw)
    except Exception:
        pass
    return max(MIN_POLL_SECONDS, min(MAX_POLL_SECONDS, value))


# Границы удержания длинного опроса. Меньше пяти секунд — это уже обычный
# опрос с его переподключениями, больше пятидесяти — соединение успевает
# порваться в туннеле или у оператора, и удержание оборачивается лишней
# работой вместо экономии.
MIN_LONG_POLL_SECONDS = 5
MAX_LONG_POLL_SECONDS = 50


def current_long_poll_seconds() -> int:
    """Сколько держать запрос длинного опроса, свежим чтением из config.json."""
    value = settings.mdm_long_poll_seconds
    try:
        data = json.loads(Path("config.json").read_text(encoding="utf-8"))
        if (raw := data.get("MDM_LONG_POLL_SECONDS")) is not None:
            value = int(raw)
    except Exception:
        pass
    return max(MIN_LONG_POLL_SECONDS, min(MAX_LONG_POLL_SECONDS, value))


# Насколько свежей должна быть отметка «на связи», чтобы не переписывать её
# заново. См. MdmService.mark_seen.
MARK_SEEN_MIN_SECONDS = 60

# Сколько ждать подтверждения от телефона, прежде чем считать команду
# потерянной. См. MdmService.expire_stale_commands.
STALE_COMMAND_SECONDS = 15 * 60


def _is_fresh(timestamp: Optional[str], max_age_seconds: int) -> bool:
    """Не старше ли отметка заданного возраста. Нечитаемая — считается старой."""
    if not timestamp:
        return False
    try:
        moment = datetime.fromisoformat(str(timestamp))
    except ValueError:
        return False
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - moment).total_seconds() < max_age_seconds


# Статусы команды, которые понимает схема. Всё, что не отсюда, — повреждённая
# запись: файл правят несколько процессов, а однажды его пришлось править и
# руками.
COMMAND_STATUSES = {"pending", "sent", "done", "failed", "canceled"}


def _sane_command(command: dict[str, Any]) -> dict[str, Any]:
    """Обезвредить одну запись команды перед проверкой схемы.

    Карточка телефона показывает историю команд, и раньше одна повреждённая
    запись роняла всю страницу MDM целиком: схема не принимала неизвестный
    статус, а падала на этом вся выдача устройств. История — не то, ради чего
    стоит терять доступ к парку, поэтому непонятный статус показываем как
    сбойный, а не отказываемся отвечать.
    """
    if command.get("status") in COMMAND_STATUSES:
        return command
    return {**command, "status": "failed"}


def current_agent_signature_checksum() -> str:
    """Отпечаток ключа подписи, свежим чтением из config.json."""
    try:
        data = json.loads(Path("config.json").read_text(encoding="utf-8"))
        if value := data.get("MDM_AGENT_SIGNATURE_CHECKSUM"):
            return str(value)
    except Exception:
        pass
    return settings.mdm_agent_signature_checksum


def current_upload_token() -> str:
    """Токен сборки, свежим чтением из config.json."""
    try:
        data = json.loads(Path("config.json").read_text(encoding="utf-8"))
        if value := data.get("MDM_UPLOAD_TOKEN"):
            return str(value)
    except Exception:
        pass
    return settings.mdm_upload_token


def apps_dir() -> Path:
    path = Path(MDM_APPS_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def library_app_url(app_id: str) -> str:
    """Ссылка, по которой телефон качает приложение из каталога.

    Как и агент, отдаётся без авторизации: телефон не может предъявить
    пользовательскую сессию, а имя файла — случайные 16 символов от хэша
    содержимого, так что перебором его не нащупать.
    """
    return settings.public_base_url.rstrip("/") + "/api/mdm/apps/" + app_id + ".apk"


def _has_android_manifest(content: bytes) -> bool:
    """Похоже ли на APK хотя бы по составу архива."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            archive.getinfo("AndroidManifest.xml")
        return True
    except Exception:
        return False


def snapshots_dir(device_id: str) -> Path:
    from app.config import MDM_SNAPSHOTS_DIR

    path = Path(MDM_SNAPSHOTS_DIR) / device_id
    path.mkdir(parents=True, exist_ok=True)
    return path


# Снимки открываются в браузере обычной ссылкой, как сканы паспорта, — но, в
# отличие от паспортов, они не публичны: это кадры с камеры. Поэтому ссылка
# подписана и живёт ограниченное время. Без действительной подписи отдача
# снимка отвечает 403, так что простой <a href> работает, а перебором адрес не
# достать.
SNAPSHOT_URL_TTL_SECONDS = 12 * 3600


def sign_snapshot(device_id: str, snapshot_id: str, exp: int) -> str:
    import hashlib
    import hmac

    message = (device_id + "/" + snapshot_id + "/" + str(exp)).encode("utf-8")
    return hmac.new(settings.secret_key.encode("utf-8"), message, hashlib.sha256).hexdigest()[:32]


def verify_snapshot_sig(device_id: str, snapshot_id: str, exp: int, sig: str) -> bool:
    import secrets as _secrets
    import time

    if exp < int(time.time()):
        return False
    expected = sign_snapshot(device_id, snapshot_id, exp)
    return _secrets.compare_digest(expected, sig or "")


def snapshot_url(device_id: str, snapshot_id: str) -> str:
    import time

    exp = int(time.time()) + SNAPSHOT_URL_TTL_SECONDS
    sig = sign_snapshot(device_id, snapshot_id, exp)
    return (
        settings.public_base_url.rstrip("/")
        + "/api/mdm/devices/" + device_id + "/snapshots/" + snapshot_id + ".jpg"
        + "?exp=" + str(exp) + "&sig=" + sig
    )


def _library_index_path() -> Path:
    return apps_dir() / "index.json"


def _read_library_index() -> dict[str, Any]:
    try:
        return json.loads(_library_index_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_library_index(index: dict[str, Any]) -> None:
    _library_index_path().write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def agent_apk_path() -> Path:
    return Path(MDM_AGENT_APK_FILE)


def agent_apk_url() -> str:
    """Адрес, по которому телефон качает агента.

    Публичный и без авторизации сознательно: по этой же ссылке APK тянет
    мастер первичной настройки Android при провижининге по QR — там ещё нет
    ни токена, ни возможности его ввести. Подмену ловит не доступ, а
    контрольная сумма подписи в самом QR.
    """
    return settings.public_base_url.rstrip("/") + "/api/mdm/agent.apk"


class MdmValidationError(ValueError):
    """Команда или политика не проходит проверку — наверх идёт как HTTP 400."""


class MdmService:
    def __init__(
        self,
        repo: Optional[MdmRepository] = None,
        schedule_repo: Optional[MdmScheduleRepository] = None,
    ) -> None:
        self._repo = repo or get_mdm_repository()
        self._schedules = schedule_repo or get_mdm_schedule_repository()

    # --- агент ----------------------------------------------------------

    def enroll(self, data: MdmEnrollRequest) -> tuple[MdmDevice, str]:
        """Регистрирует телефон и выдаёт ему персональный токен.

        Повторный enroll того же device_id не создаёт дубль, а перевыпускает
        токен: это штатный путь восстановления, когда агента переустановили и
        старый токен на телефоне потерян.
        """
        existing = self._repo.get(data.device_id)
        patch: dict[str, Any] = {
            "model": data.model,
            "manufacturer": data.manufacturer,
            "android_version": data.android_version,
            "agent_version": data.agent_version,
            "device_owner": data.device_owner,
            "last_seen_at": _now(),
        }
        if not existing:
            patch.update(
                {
                    "name": None,
                    "salon_id": None,
                    "enrolled_at": _now(),
                    "policy": MdmPolicy().model_dump(),
                    "policy_version": 1,
                    "applied_policy_version": None,
                    "commands": [],
                }
            )
        self._repo.upsert(data.device_id, patch)
        token = self._repo.issue_token(data.device_id)
        return self.get_device(data.device_id), token

    def checkin(self, device: dict[str, Any], data: MdmCheckinRequest) -> MdmDevice:
        device_id = str(device.get("id"))
        for ack in data.acks:
            self._repo.ack_command(device_id, ack.command_id, ack.status, ack.result, _now())

        patch: dict[str, Any] = {
            "model": data.model or device.get("model"),
            "manufacturer": data.manufacturer or device.get("manufacturer"),
            "android_version": data.android_version or device.get("android_version"),
            "agent_version": data.agent_version or device.get("agent_version"),
            "device_owner": data.device_owner,
            "battery": data.battery,
            "applied_policy_version": data.applied_policy_version,
            "last_error": data.last_error,
            "play_protect": data.play_protect,
            "last_seen_at": _now(),
        }
        # Телеметрия: пишем только то, что реально пришло, чтобы редкое поле не
        # затирало прежнее значение пустотой.
        for field in (
            "storage_total_mb", "storage_free_mb", "ram_total_mb", "network",
            "wifi_ssid", "ip_address", "uptime_seconds", "secure_lock",
            "can_reset_password", "screen_on", "serial_number", "imei", "sim_operator",
        ):
            value = getattr(data, field)
            if value is not None:
                patch[field] = value
        # Список приложений приезжает не каждый раз, а только когда изменился.
        # Отсутствие его в запросе — «не менялся», а не «приложений больше нет».
        if data.apps is not None:
            patch["apps"] = [app.model_dump() for app in data.apps]
            patch["apps_hash"] = data.apps_hash
            patch["apps_updated_at"] = _now()

        # Координаты приходят только в ответ на команду locate, поэтому пустое
        # значение означает «не спрашивали», а не «телефон переехал в null».
        if data.latitude is not None and data.longitude is not None:
            patch["latitude"] = data.latitude
            patch["longitude"] = data.longitude
            patch["location_at"] = data.location_at or _now()

        self._repo.upsert(device_id, patch)
        return self.get_device(device_id)

    def ack_commands(self, device: dict[str, Any], acks: list[MdmCommandAck]) -> int:
        """Записывает результаты выполненных команд. Возвращает число опознанных."""
        device_id = str(device.get("id"))
        recorded = 0
        for ack in acks:
            if self._repo.ack_command(device_id, ack.command_id, ack.status, ack.result, _now()):
                recorded += 1
        return recorded

    def set_applied_version(self, device: dict[str, Any], version: int) -> None:
        """Догоняющий отчёт агента о применённой политике.

        Без него карточка на один цикл (15 минут) показывала бы «ждёт
        применения» для политики, которая на телефоне уже действует.
        """
        self._repo.upsert(str(device.get("id")), {"applied_policy_version": version})

    def take_pending_commands(self, device_id: str) -> list[dict[str, Any]]:
        return self._repo.take_pending(device_id)

    def cancel_command(self, device_id: str, command_id: str) -> MdmDevice:
        """Снять из очереди команду, которая ещё не ушла на телефон.

        Ошибиться кнопкой здесь дорого — рядом стоят `wipe` и `release_owner`, —
        а с длинным опросом запас времени на исправление измеряется секундами.
        Отменять уже отправленное поздно и нечестно: телефон её выполнил или
        выполняет, и отметка «отменено» соврала бы оператору.
        """
        if not self._repo.get(device_id):
            raise MdmValidationError("device_not_found")
        if not self._repo.cancel_command(device_id, command_id):
            raise MdmValidationError("command_not_cancelable")
        return self.get_device(device_id)

    def expire_stale_commands(self, device_id: str) -> int:
        """Пометить сбойными команды, которые телефон забрал и не подтвердил.

        Подтверждение может не прийти совсем: прошивка убила процесс между
        исполнением и отчётом. Такая команда висела бы в панели со статусом
        «на телефоне» вечно, и оператор не отличил бы её от медленной установки.
        Врать бесконечно хуже, чем через десять минут признать, что ответа нет.

        Порог с запасом: установка большого APK и снимок с камеры укладываются
        в минуты, а не в десятки.
        """
        device = self._repo.get(device_id)
        if not device:
            return 0
        commands = list(device.get("commands") or [])
        changed = 0
        for command in commands:
            if command.get("status") != "sent":
                continue
            if _is_fresh(command.get("created_at"), STALE_COMMAND_SECONDS):
                continue
            command["status"] = "failed"
            command["result"] = "телефон не подтвердил выполнение"
            changed += 1
        if changed:
            self._repo.upsert(str(device_id), {"commands": commands})
        return changed

    def queue_marker(self) -> tuple[float, int]:
        """Признак «очередь могла измениться» для длинного опроса."""
        return self._repo.marker()

    def mark_seen(self, device_id: str) -> None:
        """Отметить телефон живым, не собирая с него отчёт.

        Длинный опрос приходит куда чаще полного чек-ина, и именно он теперь
        доказывает, что телефон на связи: без этой отметки сторож считал бы
        замолчавшим аппарат, который на самом деле висит на открытом запросе.

        Отметка придушена по времени. Каждый телефон переподключается раз в
        25 секунд, а запись здесь переписывает файл целиком — на парке салонов
        это была бы непрерывная перезапись мегабайтного файла и столь же
        непрерывное пробуждение всех открытых панелей. Сторож меряет молчание
        десятками минут, так что минутной точности ему хватает с запасом.
        """
        device = self._repo.get(device_id)
        if device and _is_fresh(device.get("last_seen_at"), MARK_SEEN_MIN_SECONDS):
            return
        self._repo.upsert(str(device_id), {"last_seen_at": _now()})

    def find_by_token(self, token: str) -> Optional[dict[str, Any]]:
        return self._repo.get_by_token(token)

    # --- админка --------------------------------------------------------

    def list_devices(self) -> list[MdmDevice]:
        return [self._to_schema(d) for d in self._repo.list()]

    def get_device(self, device_id: str) -> MdmDevice:
        device = self._repo.get(device_id)
        if not device:
            raise MdmValidationError("device_not_found")
        return self._to_schema(device)

    def update_device(self, device_id: str, data: MdmDeviceUpdate) -> MdmDevice:
        if not self._repo.get(device_id):
            raise MdmValidationError("device_not_found")
        patch = {k: v for k, v in data.model_dump(exclude_unset=True).items()}
        self._repo.upsert(device_id, patch)
        return self.get_device(device_id)

    def set_policy(self, device_id: str, policy: MdmPolicy) -> MdmDevice:
        device = self._repo.get(device_id)
        if not device:
            raise MdmValidationError("device_not_found")
        if policy.kiosk.enabled and not policy.kiosk.home and not policy.kiosk.packages:
            raise MdmValidationError("kiosk_requires_app")

        self._repo.upsert(
            device_id,
            {
                "policy": policy.model_dump(),
                # Версия — единственное, по чему агент понимает, что политика
                # изменилась, поэтому растёт при каждом сохранении, даже если
                # содержимое совпало с предыдущим.
                "policy_version": int(device.get("policy_version") or 1) + 1,
            },
        )
        return self.get_device(device_id)

    def queue_command(self, device_id: str, data: MdmCommandCreate) -> dict[str, Any]:
        if not self._repo.get(device_id):
            raise MdmValidationError("device_not_found")

        params = dict(data.params or {})
        if data.type == "install_apk":
            url = str(params.get("url") or "").strip()
            if not url.startswith("https://"):
                # http:// пустили бы APK по открытому каналу — подменить его в
                # пути до телефона тривиально, а ставится он молча и с правами
                # владельца устройства.
                raise MdmValidationError("install_apk_requires_https_url")
            params["url"] = url
        elif data.type in ("uninstall", "clear_app_data"):
            package = str(params.get("package") or "").strip()
            if not package:
                raise MdmValidationError(data.type + "_requires_package")
            params["package"] = package
        elif data.type == "set_app_enabled":
            package = str(params.get("package") or "").strip()
            if not package:
                raise MdmValidationError("set_app_enabled_requires_package")
            params["package"] = package
            params["enabled"] = bool(params.get("enabled", True))
        elif data.type == "message":
            # Пустой текст снимает сообщение с экрана — это законный сценарий,
            # поэтому длину не требуем, только ограничиваем сверху.
            params["text"] = str(params.get("text") or "")[:400]
        elif data.type == "wake":
            # Держать экран включённым дольше пяти минут по команде незачем:
            # телефон лежит без присмотра, а разбудить его снова — одна кнопка.
            secs = int(params.get("seconds") or 60)
            params["seconds"] = max(5, min(300, secs))
            params["show_home"] = bool(params.get("show_home", True))
        elif data.type == "set_play_protect":
            params["enabled"] = bool(params.get("enabled", False))
        elif data.type == "set_password":
            # Пустой пароль — законное «снять блокировку». Непустой ограничиваем
            # снизу: Android короче четырёх символов не примет, и лучше сказать
            # это здесь, чем получить отказ с телефона через полминуты.
            password = str(params.get("password") or "")
            if password and len(password) < 4:
                raise MdmValidationError("password_too_short")
            params["password"] = password
        elif data.type == "alert":
            # В отличие от message, пустой текст здесь бессмыслен: показывать
            # сотруднику во весь экран нечего, а закрыть окно нельзя будет,
            # если ещё и снята кнопка. Убирают его командой stop_alert.
            text = str(params.get("text") or "").strip()
            if not text:
                raise MdmValidationError("alert_requires_text")
            params["text"] = text[:600]
            params["title"] = str(params.get("title") or "").strip()[:120]
            params["dismissible"] = bool(params.get("dismissible", True))
        elif data.type == "ring":
            secs = int(params.get("seconds") or 30)
            params["seconds"] = max(5, min(300, secs))
        elif data.type == "set_volume":
            pct = int(params.get("percent") or 100)
            params["percent"] = max(0, min(100, pct))
        elif data.type == "launch_app":
            package = str(params.get("package") or "").strip()
            if not package:
                raise MdmValidationError("launch_app_requires_package")
            params["package"] = package
        elif data.type == "grant_permission":
            package = str(params.get("package") or "").strip()
            permission = str(params.get("permission") or "").strip()
            if not package or not permission:
                raise MdmValidationError("grant_permission_requires_package_and_permission")
            params["package"] = package
            params["permission"] = permission
            params["grant"] = bool(params.get("grant", True))
        elif data.type == "set_time_zone":
            zone = str(params.get("zone") or "").strip()
            if not zone:
                raise MdmValidationError("set_time_zone_requires_zone")
            params["zone"] = zone
        elif data.type == "set_auto_time":
            params["enabled"] = bool(params.get("enabled", True))
        elif data.type == "add_wifi":
            ssid = str(params.get("ssid") or "").strip()
            if not ssid:
                raise MdmValidationError("add_wifi_requires_ssid")
            params["ssid"] = ssid
            params["password"] = str(params.get("password") or "")
            params["hidden"] = bool(params.get("hidden", False))
        elif data.type == "set_stay_awake":
            params["enabled"] = bool(params.get("enabled", True))
        elif data.type == "set_status_bar":
            params["disabled"] = bool(params.get("disabled", True))
        elif data.type == "set_time":
            epoch = int(params.get("epoch_ms") or 0)
            if epoch <= 0:
                raise MdmValidationError("set_time_requires_epoch_ms")
            params["epoch_ms"] = epoch

        command = {
            "id": uuid.uuid4().hex,
            "type": data.type,
            "params": params,
            "created_at": _now(),
            "status": "pending",
            "result": None,
            "acked_at": None,
        }
        self._repo.add_command(device_id, command)
        # Сообщение на экране блокировки показываем в карточке сразу, не дожидаясь
        # чек-ина: оператор должен видеть, что он задал.
        if data.type == "message":
            self._repo.upsert(device_id, {"lock_message": params.get("text") or None})
        return command

    # --- расписания ------------------------------------------------------

    def list_schedules(self) -> list[MdmSchedule]:
        return [MdmSchedule.model_validate(s) for s in self._schedules.list()]

    def add_schedule(self, data: MdmScheduleCreate) -> MdmSchedule:
        # Проверяем команду один раз тем же путём, что и обычную постановку:
        # расписание не должно молча копить кривую команду до срабатывания.
        hh, _, mm = data.time.partition(":")
        if not (hh.isdigit() and mm.isdigit() and 0 <= int(hh) < 24 and 0 <= int(mm) < 60):
            raise MdmValidationError("schedule_bad_time")
        MdmCommandCreate(type=data.command_type, params=data.command_params)  # валидация типа
        stored = self._schedules.add(data.model_dump())
        return MdmSchedule.model_validate(stored)

    def delete_schedule(self, schedule_id: str) -> None:
        if not self._schedules.delete(schedule_id):
            raise MdmValidationError("schedule_not_found")

    def run_due_schedules(self, now_hhmm: str, today: str) -> int:
        """Выполнить расписания, чьё время настало и сегодня ещё не запускались.

        Вызывается таймером раз в минуту. Возвращает число сработавших.
        """
        fired = 0
        for s in self._schedules.list():
            if not s.get("enabled", True):
                continue
            if s.get("time") != now_hhmm:
                continue
            if s.get("last_run_date") == today:
                continue  # уже сработало сегодня
            command = MdmCommandCreate(
                type=s.get("command_type"), params=dict(s.get("command_params") or {})
            )
            target = str(s.get("target") or "all")
            if target.startswith("device:"):
                try:
                    self.queue_command(target.split(":", 1)[1], command)
                except MdmValidationError:
                    pass
            else:
                salon = target.split(":", 1)[1] if target.startswith("salon:") else None
                self.broadcast_command(command, salon)
            self._schedules.mark_run(str(s.get("id")), today)
            fired += 1
        return fired

    def lost_mode(self, device_id: str, message: Optional[str] = None) -> list[dict[str, Any]]:
        """Режим пропажи: одной кнопкой заблокировать, показать сообщение на
        экране, поднять сигнал, запросить координаты и снять кадр с камеры.

        Просто последовательность обычных команд — телефон исполнит их подряд на
        ближайшей связи. Порядок осмысленный: сперва блокировка и сообщение
        (чтобы нашедший сразу понял, чей телефон и куда звонить), потом сигнал и
        локация с камерой для поиска.
        """
        text = (message or "").strip() or "Телефон потерян. Пожалуйста, верните владельцу."
        steps = [
            MdmCommandCreate(type="lock"),
            MdmCommandCreate(type="message", params={"text": text}),
            MdmCommandCreate(type="ring", params={"seconds": 60}),
            MdmCommandCreate(type="locate"),
            MdmCommandCreate(type="camera", params={"lens": "back"}),
        ]
        return [self.queue_command(device_id, step) for step in steps]

    def found_mode(self, device_id: str) -> list[dict[str, Any]]:
        """Отбой пропажи: телефон нашёлся.

        Снимает ровно то, что режим пропажи оставил включённым и что само не
        погаснет: сигнал и сообщение на экране блокировки. Разбирать это руками
        по одной команде — тот случай, когда обратное действие сложнее прямого,
        а нужно оно в спешке.

        Блокировку экрана не трогаем: она снимается тем же PIN-ом, что и всегда,
        и «разблокировать удалённо» означало бы снять защиту с найденного
        телефона — ровно наоборот тому, зачем режим включали.
        """
        steps = [
            MdmCommandCreate(type="stop_ring"),
            MdmCommandCreate(type="message", params={"text": ""}),
        ]
        return [self.queue_command(device_id, step) for step in steps]

    def broadcast_command(self, data: MdmCommandCreate, salon_id: Optional[str] = None) -> "MdmBroadcastResult":
        """Поставить команду сразу всем телефонам (или всем в одном салоне).

        Валидация — та же, что у одиночной команды: проверяем один раз на
        болванке, потом ставим каждому. Так кривая команда не уедет половине
        парка, прежде чем упасть.
        """
        from app.schemas.mdm import MdmBroadcastResult

        devices = self._repo.list()
        if salon_id:
            devices = [d for d in devices if str(d.get("salon_id") or "") == str(salon_id)]

        queued = 0
        for device in devices:
            try:
                self.queue_command(str(device.get("id")), data)
                queued += 1
            except MdmValidationError:
                # Одна и та же команда всем: если не прошла валидацию, она не
                # пройдёт нигде — пробрасываем наверх как ошибку запроса.
                raise
        return MdmBroadcastResult(queued=queued, total=len(devices))

    def delete_device(self, device_id: str) -> None:
        """Убирает телефон из списка. Сам телефон при этом остаётся управляемым.

        Снять управление можно только на самом устройстве (сбросом или командой
        wipe) — удаление карточки лишь означает «мы им больше не занимаемся»,
        и агент, оставшийся на телефоне, начнёт получать 401 на чек-инах.
        """
        if not self._repo.delete(device_id):
            raise MdmValidationError("device_not_found")

    # --- каталог приложений ---------------------------------------------

    def list_library(self) -> list[MdmLibraryApp]:
        index = _read_library_index()
        installed = self._installed_counts()
        result: list[MdmLibraryApp] = []
        for app_id, meta in index.items():
            path = apps_dir() / (app_id + ".apk")
            if not path.exists():
                continue
            package = meta.get("package")
            result.append(
                MdmLibraryApp(
                    id=app_id,
                    filename=meta.get("filename") or (app_id + ".apk"),
                    package=package,
                    version_name=meta.get("version_name"),
                    version_code=meta.get("version_code"),
                    size=path.stat().st_size,
                    uploaded_at=meta.get("uploaded_at"),
                    url=library_app_url(app_id),
                    kind=meta.get("kind", "apk"),
                    parts=int(meta.get("parts") or 1),
                    has_obb=bool(meta.get("has_obb")),
                    installed_on=installed.get(package, 0) if package else 0,
                )
            )
        result.sort(key=lambda a: str(a.uploaded_at or ""), reverse=True)
        return result

    def save_library_app(self, filename: str, content: bytes) -> MdmLibraryApp:
        # Принимаем и одиночный APK, и контейнер вроде XAPK: у приложений,
        # которые Google раздаёт набором, единого файла попросту не бывает.
        info = read_package_info(content)
        kind = info["kind"]
        if kind is None:
            # Разобрать не вышло — но если внутри лежит манифест Android, это
            # APK, и он поставится: установщик разберётся сам. Наш разбор —
            # «лучшее усилие», решать за пользователя, годится ли файл, он не
            # должен.
            if _has_android_manifest(content):
                kind = "apk"
            else:
                raise MdmValidationError("not_an_apk")

        app_id = hashlib.sha256(content).hexdigest()[:16]
        (apps_dir() / (app_id + ".apk")).write_bytes(content)

        index = _read_library_index()
        index[app_id] = {
            "filename": filename,
            "package": info["package"],
            "version_name": info["version_name"],
            "version_code": info["version_code"],
            "kind": kind,
            "parts": info["parts"],
            "has_obb": info["has_obb"],
            "uploaded_at": _now(),
        }
        _write_library_index(index)

        return next(app for app in self.list_library() if app.id == app_id)

    def delete_library_app(self, app_id: str) -> None:
        index = _read_library_index()
        if app_id not in index:
            raise MdmValidationError("app_not_found")
        (apps_dir() / (app_id + ".apk")).unlink(missing_ok=True)
        index.pop(app_id, None)
        _write_library_index(index)

    def library_app_path(self, app_id: str) -> Path:
        path = apps_dir() / (app_id + ".apk")
        if not path.exists():
            raise MdmValidationError("app_not_found")
        return path

    def install_library_app(self, device_id: str, app_id: str) -> dict[str, Any]:
        if app_id not in _read_library_index():
            raise MdmValidationError("app_not_found")
        return self.queue_command(
            device_id,
            MdmCommandCreate(type="install_apk", params={"url": library_app_url(app_id)}),
        )

    def _installed_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for device in self._repo.list():
            for app in device.get("apps") or []:
                package = app.get("package")
                if package:
                    counts[package] = counts.get(package, 0) + 1
        return counts

    # --- снимки с камеры ------------------------------------------------

    def save_snapshot(self, device: dict[str, Any], lens: Optional[str], content: bytes) -> str:
        device_id = str(device.get("id"))
        snapshot_id = uuid.uuid4().hex
        (snapshots_dir(device_id) / (snapshot_id + ".jpg")).write_bytes(content)

        # Свежий список из репозитория, а не из переданного device: тот пришёл
        # из поиска по токену и к моменту нескольких снимков подряд устаревает.
        stored = self._repo.get(device_id) or device
        # Держим по одному последнему снимку на камеру: новый кадр задней камеры
        # затирает прежний кадр задней, фронтальный — прежний фронтальный.
        # Копить историю незачем, а два свежих кадра отвечают на вопрос «что
        # видит телефон» и не растят каталог.
        bucket = lens or "back"
        kept: list[dict[str, Any]] = []
        for snap in stored.get("snapshots") or []:
            if (snap.get("lens") or "back") == bucket:
                # Файл вытесняемого кадра удаляем, иначе он осиротеет на диске.
                (snapshots_dir(device_id) / (str(snap.get("id")) + ".jpg")).unlink(missing_ok=True)
            else:
                kept.append(snap)
        kept.append(
            {
                "id": snapshot_id,
                "lens": lens,
                "taken_at": _now(),
                "size": len(content),
            }
        )
        self._repo.upsert(device_id, {"snapshots": kept})
        return snapshot_id

    def snapshot_path(self, device_id: str, snapshot_id: str) -> Path:
        # snapshot_id — это hex из uuid4, но приходит из URL, поэтому не пускаем
        # в путь ничего, кроме hex: защита от «../» и прочего обхода каталога.
        if not all(c in "0123456789abcdef" for c in snapshot_id):
            raise MdmValidationError("snapshot_not_found")
        path = snapshots_dir(device_id) / (snapshot_id + ".jpg")
        if not path.exists():
            raise MdmValidationError("snapshot_not_found")
        return path

    # --- провижининг по QR ----------------------------------------------

    def provisioning(self) -> MdmProvisioning:
        """Строка для QR, который читает мастер первичной настройки Android.

        Ключи с длинными именами — не наша выдумка, это протокол Android; их
        состав и написание менять нельзя. Смысловая часть три:
        откуда качать агента, чем проверить его подлинность и что передать ему
        внутрь, чтобы телефон зарегистрировался сам, без ввода руками.
        """
        problems: list[str] = []
        checksum = current_agent_signature_checksum()
        key = current_enroll_key()
        info = self.agent_info()

        if not info.available:
            problems.append("APK агента не загружен на сервер")
        if not checksum:
            problems.append("Не задан MDM_AGENT_SIGNATURE_CHECKSUM в config.json")
        if not key:
            problems.append("Не задан MDM_ENROLL_KEY в config.json")
        if problems:
            return MdmProvisioning(ready=False, problems=problems)

        payload = {
            "android.app.extra.PROVISIONING_DEVICE_ADMIN_COMPONENT_NAME": (
                "pw.bonjour.mdm/pw.bonjour.mdm.AdminReceiver"
            ),
            "android.app.extra.PROVISIONING_DEVICE_ADMIN_SIGNATURE_CHECKSUM": checksum,
            "android.app.extra.PROVISIONING_DEVICE_ADMIN_PACKAGE_DOWNLOAD_LOCATION": (
                agent_apk_url()
            ),
            # Системные приложения остаются: без этого телефон приедет к
            # сотруднику без камеры, календаря и половины привычных вещей.
            "android.app.extra.PROVISIONING_LEAVE_ALL_SYSTEM_APPS_ENABLED": True,
            "android.app.extra.PROVISIONING_SKIP_ENCRYPTION": False,
            "android.app.extra.PROVISIONING_ADMIN_EXTRAS_BUNDLE": {
                "server_url": settings.public_base_url.rstrip("/"),
                "enroll_key": key,
            },
        }
        return MdmProvisioning(ready=True, payload=json.dumps(payload, ensure_ascii=False))

    # --- APK агента -----------------------------------------------------

    def agent_info(self) -> MdmAgentInfo:
        path = agent_apk_path()
        if not path.exists():
            return MdmAgentInfo(available=False)

        raw = path.read_bytes()
        version_name, version_code = self._read_apk_version(raw)
        outdated = 0
        if version_name:
            outdated = sum(
                1
                for d in self._repo.list()
                if (d.get("agent_version") or "") != version_name
            )
        return MdmAgentInfo(
            available=True,
            version_name=version_name,
            version_code=version_code,
            size=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
            uploaded_at=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
            url=agent_apk_url(),
            outdated_devices=outdated,
        )

    def save_agent_apk(self, content: bytes) -> MdmAgentInfo:
        """Кладёт новый APK агента на сервер.

        Проверка здесь — не подпись, а вменяемость: что это вообще APK и что
        внутри наш пакет. Полноценно проверить подпись в питоне нечем, но и
        цена ошибки другая: телефон откажется ставить чужой APK поверх агента,
        потому что ключ не совпадёт. Смысл проверки — поймать «залил не тот
        файл» до того, как команда уйдёт на весь парк.
        """
        try:
            archive = zipfile.ZipFile(io.BytesIO(content))
            manifest = archive.read("AndroidManifest.xml")
        except Exception as exc:
            raise MdmValidationError("not_an_apk") from exc

        if "pw.bonjour.mdm".encode("utf-16-le") not in manifest:
            raise MdmValidationError("foreign_apk")

        # Откат на версию старее не имеет смысла и опасен: Android откажется
        # ставить её поверх новой, и весь парк отчитается ошибкой установки.
        # Проверено на себе — загрузил в панель залежавшийся файл и откатил
        # сервер на четыре версии назад.
        new_code = self._read_apk_version(content)[1]
        current_code = self.agent_info().version_code
        if new_code is not None and current_code is not None and new_code < current_code:
            raise MdmValidationError(
                f"agent_downgrade_{current_code}_to_{new_code}"
            )

        agent_apk_path().write_bytes(content)
        return self.agent_info()

    def rollout_agent_update(self) -> MdmAgentRolloutResult:
        """Ставит команду обновления телефонам, чья версия отличается от лежащей.

        Сравнение по имени версии, а не «новее/старее»: откат на предыдущую
        версию — такой же законный сценарий, как обновление, и запрещать его
        сравнением номеров незачем.
        """
        info = self.agent_info()
        if not info.available:
            raise MdmValidationError("agent_apk_not_uploaded")
        if not info.version_name:
            # Версии нет — значит APK собран до того, как её начали класть
            # внутрь. Рассылать вслепую нельзя: обновим все телефоны в цикле.
            raise MdmValidationError("agent_apk_version_unknown")

        queued = skipped = 0
        for device in self._repo.list():
            if (device.get("agent_version") or "") == info.version_name:
                skipped += 1
                continue
            self.queue_command(
                str(device.get("id")),
                MdmCommandCreate(type="install_apk", params={"url": info.url}),
            )
            queued += 1
        return MdmAgentRolloutResult(queued=queued, skipped=skipped)

    @staticmethod
    def _read_apk_version(content: bytes) -> tuple[Optional[str], Optional[int]]:
        """Версия лежит в assets/agent_version.json, который кладёт сборка.

        Разбирать бинарный манифест Android ради двух чисел — несоразмерно, а
        имя файла по дороге может стать каким угодно.
        """
        try:
            archive = zipfile.ZipFile(io.BytesIO(content))
            data = json.loads(archive.read("assets/agent_version.json").decode("utf-8"))
            return str(data["version_name"]), int(data["version_code"])
        except Exception:
            return None, None

    def set_command_poll_seconds(self, value: int) -> MdmEnrollmentInfo:
        """Меняет частоту опроса команд, записывая её в config.json.

        Пишем через ConfigService, а не своими руками: у этого файла уже была
        история с затиранием (чтение повреждённого как {} и запись обратно), и
        там для этого есть атомарная запись с бэкапом и блокировкой.
        """
        if not MIN_POLL_SECONDS <= value <= MAX_POLL_SECONDS:
            raise MdmValidationError("poll_seconds_out_of_range")
        from app.services.config_service import ConfigService

        ConfigService().patch({"MDM_COMMAND_POLL_SECONDS": int(value)})
        return self.enrollment_info()

    def enrollment_info(self) -> MdmEnrollmentInfo:
        key = current_enroll_key()
        return MdmEnrollmentInfo(
            server_url=settings.public_base_url,
            enroll_key=key,
            configured=bool(key),
            command_poll_seconds=current_command_poll_seconds(),
        )

    # --- вспомогательное ------------------------------------------------

    @staticmethod
    def _to_schema(device: dict[str, Any]) -> MdmDevice:
        data = {k: v for k, v in device.items() if k != "token"}
        data.setdefault("policy", MdmPolicy().model_dump())
        device_id = str(device.get("id"))
        # url снимка нигде не хранится — считаем на лету от public_base_url,
        # чтобы смена домена не осиротила ссылки в карточках.
        data["snapshots"] = [
            {**s, "url": snapshot_url(device_id, str(s.get("id")))}
            for s in (device.get("snapshots") or [])
        ]
        data["commands"] = [_sane_command(c) for c in (device.get("commands") or [])]
        return MdmDevice.model_validate(data)


_service: Optional[MdmService] = None


def get_mdm_service() -> MdmService:
    global _service
    if _service is None:
        _service = MdmService()
    return _service
