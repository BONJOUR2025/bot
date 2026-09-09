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
