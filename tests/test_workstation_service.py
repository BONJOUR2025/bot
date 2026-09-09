import pytest

from app.data.workstation_repository import WorkstationRepository
from app.schemas.workstation import (
    DiskInfo,
    WorkstationCheckin,
    WorkstationEnrollRequest,
    WorkstationUpdate,
)
from app.services.workstation_service import (
    WorkstationService,
    WorkstationValidationError,
)


@pytest.fixture
def service(tmp_path):
    return WorkstationService(repo=WorkstationRepository(file_path=str(tmp_path / "ws.json")))


def enroll(service, hostname="SALON-KASSA-1"):
    return service.enroll(WorkstationEnrollRequest(hostname=hostname, agent_version="0.1.0"))


def test_reenroll_same_hostname_keeps_card_but_rotates_token(service):
    """Повторный запуск агента на том же ПК не должен плодить карточки.

    Иначе после каждой переустановки в панели оставался бы мёртвый двойник,
    и «молчит уже сутки» приходило бы про машину, которая рядом работает.
    """
    first_id, first_token = enroll(service)
    second_id, second_token = enroll(service)

    assert first_id == second_id
    assert first_token != second_token
    assert len(service.list_workstations()) == 1
    assert service.find_by_token(first_token) is None
    assert service.find_by_token(second_token)["id"] == second_id


def test_token_is_never_exposed(service):
    _, token = enroll(service)
    dumped = service.list_workstations()[0].model_dump()
    assert "token" not in dumped
    assert token not in str(dumped)


def test_checkin_keeps_previous_values_when_field_missing(service):
    """Сбор отдельного показателя может не удаться — это не повод затирать
    прежнее значение пустотой и показывать оператору пустую карточку."""
    ws_id, token = enroll(service)
    raw = service.find_by_token(token)
    service.checkin(raw, WorkstationCheckin(os_version="Windows 10 22H2", ram_total_mb=8192))

    service.checkin(service.find_by_token(token), WorkstationCheckin(cpu_percent=12.5))

    after = service.get(ws_id)
    assert after.os_version == "Windows 10 22H2"
    assert after.ram_total_mb == 8192
    assert after.cpu_percent == 12.5


def test_low_disk_is_a_problem(service):
    """Место на диске — главный повод для тревоги: при переполнении встаёт
    Firebird, а вместе с ним продажи салона."""
    ws_id, token = enroll(service)
    service.checkin(service.find_by_token(token), WorkstationCheckin(
        disks=[
            DiskInfo(mount="C:", total_gb=200, free_gb=80, free_percent=40),
            DiskInfo(mount="D:", total_gb=500, free_gb=3.2, free_percent=0.6),
        ],
    ))

    problems = WorkstationService.problems(service._repo.get(ws_id))

    assert len(problems) == 1
    assert "D:" in problems[0]


def test_stopped_process_is_a_problem(service):
    ws_id, token = enroll(service)
    service.checkin(service.find_by_token(token), WorkstationCheckin(
        processes={"fbserver.exe": True, "Agbis.exe": False},
    ))

    problems = WorkstationService.problems(service._repo.get(ws_id))

    assert problems == ["не запущен Agbis.exe"]


def test_healthy_machine_has_no_problems(service):
    ws_id, token = enroll(service)
    service.checkin(service.find_by_token(token), WorkstationCheckin(
        disks=[DiskInfo(mount="C:", total_gb=200, free_gb=80, free_percent=40)],
        processes={"fbserver.exe": True},
        pending_reboot=False,
    ))

    assert WorkstationService.problems(service._repo.get(ws_id)) == []


def test_rename_and_delete(service):
    ws_id, _ = enroll(service)

    renamed = service.update(ws_id, WorkstationUpdate(name="Касса Озерки", salon_id="ozerki"))
    assert renamed.name == "Касса Озерки"

    service.delete(ws_id)
    assert service.list_workstations() == []
    with pytest.raises(WorkstationValidationError, match="workstation_not_found"):
        service.get(ws_id)


# --- команды ---------------------------------------------------------------


def _allow(monkeypatch, apps):
    """Белый список — только ИМЕНА: пути лежат в agent.ini на самой машине,
    чтобы сервер не мог указать произвольный файл."""
    import app.services.workstation_service as module
    monkeypatch.setattr(module, "current_allowed_apps", lambda: apps)


def test_run_app_rejects_program_outside_whitelist(service, monkeypatch):
    """Имя программы — ссылка на белый список сервера, а не свободный параметр.

    Иначе run_app превратился бы в «выполнить что угодно» на кассовом ПК.
    """
    from app.schemas.workstation import WorkstationCommandCreate

    ws_id, _ = enroll(service)
    _allow(monkeypatch, ["agbis"])

    with pytest.raises(WorkstationValidationError, match="app_not_allowed"):
        service.queue_command(ws_id, WorkstationCommandCreate(
            type="run_app", params={"app": r"C:\Windows\System32\cmd.exe"}))

    ok = service.queue_command(ws_id, WorkstationCommandCreate(
        type="run_app", params={"app": "agbis"}))
    assert ok["params"]["app"] == "agbis"


def test_empty_whitelist_allows_nothing(service, monkeypatch):
    """Пустой список по умолчанию — правильное поведение: пока оператор не
    перечислил программы явно, запускать нечего."""
    from app.schemas.workstation import WorkstationCommandCreate

    ws_id, _ = enroll(service)
    _allow(monkeypatch, [])

    with pytest.raises(WorkstationValidationError, match="app_not_allowed"):
        service.queue_command(ws_id, WorkstationCommandCreate(
            type="restart_process", params={"app": "agbis"}))


def test_reboot_gets_a_delay_by_default(service):
    """Мгновенное выключение посреди рабочего дня стоит дороже минуты
    ожидания: человек за кассой должен успеть закрыть смену."""
    from app.schemas.workstation import WorkstationCommandCreate

    ws_id, _ = enroll(service)

    default = service.queue_command(ws_id, WorkstationCommandCreate(type="reboot"))
    huge = service.queue_command(ws_id, WorkstationCommandCreate(
        type="reboot", params={"delay_seconds": 99999}))

    assert default["params"]["delay_seconds"] == 60
    assert huge["params"]["delay_seconds"] == 3600


def test_message_requires_text(service):
    from app.schemas.workstation import WorkstationCommandCreate

    ws_id, _ = enroll(service)
    with pytest.raises(WorkstationValidationError, match="message_requires_text"):
        service.queue_command(ws_id, WorkstationCommandCreate(
            type="message", params={"text": "   "}))


def test_pending_command_is_taken_once(service):
    from app.schemas.workstation import WorkstationCommandCreate

    ws_id, _ = enroll(service)
    cmd = service.queue_command(ws_id, WorkstationCommandCreate(type="lock"))

    first = service.take_pending_commands(ws_id)
    second = service.take_pending_commands(ws_id)

    assert [c["id"] for c in first] == [cmd["id"]]
    assert second == []


def test_cancel_only_while_pending(service):
    from app.schemas.workstation import WorkstationCommandCreate

    ws_id, _ = enroll(service)
    cmd = service.queue_command(ws_id, WorkstationCommandCreate(type="reboot"))

    assert service.cancel_command(ws_id, cmd["id"]).commands[-1].status == "canceled"

    sent = service.queue_command(ws_id, WorkstationCommandCreate(type="lock"))
    service.take_pending_commands(ws_id)
    with pytest.raises(WorkstationValidationError, match="command_not_cancelable"):
        service.cancel_command(ws_id, sent["id"])


def test_stale_sent_command_is_marked_failed(service):
    """Выключенный этой же командой компьютер уже не подтвердит выполнение —
    вечное «на компьютере» в панели врёт."""
    from datetime import datetime, timedelta, timezone as tz

    from app.schemas.workstation import WorkstationCommandCreate

    ws_id, _ = enroll(service)
    fresh = service.queue_command(ws_id, WorkstationCommandCreate(type="lock"))
    stale = service.queue_command(ws_id, WorkstationCommandCreate(type="shutdown"))
    service.take_pending_commands(ws_id)

    raw = service._repo.get(ws_id)
    for c in raw["commands"]:
        if c["id"] == stale["id"]:
            c["created_at"] = (datetime.now(tz.utc) - timedelta(hours=1)).isoformat()
    service._repo.replace_commands(ws_id, raw["commands"])

    assert service.expire_stale_commands(ws_id) == 1
    by_id = {c.id: c for c in service.get(ws_id).commands}
    assert by_id[stale["id"]].status == "failed"
    assert by_id[fresh["id"]].status == "sent"


def test_checkin_carries_acks(service):
    """Подтверждения едут вместе с отчётом: агент исполнил команду и тут же
    снова встаёт на ожидание, отдельный отчёт был бы вторым запросом зря."""
    from app.schemas.workstation import WorkstationCommandAck, WorkstationCommandCreate

    ws_id, token = enroll(service)
    cmd = service.queue_command(ws_id, WorkstationCommandCreate(type="lock"))
    service.take_pending_commands(ws_id)

    service.checkin(service.find_by_token(token), WorkstationCheckin(
        acks=[WorkstationCommandAck(command_id=cmd["id"], status="done", result="экран заблокирован")],
    ))

    stored = service.get(ws_id).commands[-1]
    assert stored.status == "done"
    assert stored.acked_at
