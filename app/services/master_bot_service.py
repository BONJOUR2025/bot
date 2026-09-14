"""Данные для бота мастера: заработок, незакрытые работы, потолок аванса.

Почему отдельный модуль, а не расширение masters_service: там админский
отчёт по всем мастерам сразу, здесь — срез по одному человеку, с правилами
видимости и с ученической стипендией поверх процента.

Два принципа, на которых всё держится:

1. Мастер опознаётся по Agbis USERS.USER_ID (поле external_code в карточке
   сотрудника), а не по строке «Фамилия И.». Строковый матчинг здесь врёт:
   Корягин сканирует под учёткой «Корягин К.», а карточка в боте называется
   «Константин К.»; Галиулин — под «Рудем Г.». Показать мастеру чужую
   зарплату — единственная ошибка, которую эта фича не имеет права сделать,
   поэтому сопоставление только по числовому id.

2. Бот никогда не считает отчёт сам. Он берёт только те периоды, которые
   warmer уже держит горячими в общем дисковом кэше (fdb_cache пишет в
   hr.db, поэтому процесс бота видит то же, что насчитал API-процесс).
   masters.works — самый дорогой запрос в системе (~17 с на спокойном
   сервере, за 100 с на загруженном) и именно он уронил дашборд 18.07.2026,
   когда ретраи начали множить параллельные запросы. Девять мастеров с
   телефонами в кармане воспроизвели бы это мгновенно.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Optional

from app.data.employee_repository import EmployeeRepository
from app.data.payout_repository import PayoutRepository
from app.services.masters_service import APPRENTICE_POSITION, APPRENTICE_DAY_RATE

logger = logging.getLogger(__name__)


# Должности, которым бот показывает раздел мастера. Список закрытый и
# намеренно не включает «Мастер по изготовлению подошвы» (Семина М.): она
# не сканирует на постах мастеров вообще, и отчёт показал бы ей ноль.
MASTER_POSITIONS: frozenset[str] = frozenset({
    "Мастер по ремонту",
    "Мастер по химчистке",
    APPRENTICE_POSITION,
})

# Периоды, которые warmer держит горячими (fdb_cache.TIER_PERIODS).
# Ничего за пределами этого набора бот не предлагает — иначе запрос уходит
# в Firebird живьём.
PERIOD_MONTH = "month"
PERIOD_PREV_MONTH = "prev_month"

PERIOD_LABELS = {
    PERIOD_MONTH: "текущий месяц",
    PERIOD_PREV_MONTH: "прошлый месяц",
}


@dataclass
class Master:
    """Мастер, опознанный и в боте, и в Агбисе."""
    employee_id: str
    name: str
    position: str
    agbis_user_id: int

    @property
    def is_apprentice(self) -> bool:
        return self.position == APPRENTICE_POSITION


def is_master_position(position: str | None) -> bool:
    return str(position or "").strip() in MASTER_POSITIONS


def resolve_master(employee_id: str | int) -> Optional[Master]:
    """Карточка сотрудника -> Master, если он мастер и привязан к Агбису.

    None означает «раздел мастера этому человеку не показываем»: либо
    должность не мастерская, либо в карточке не проставлен external_code
    (без него мы не знаем, чьи сканы показывать, и молча показать чужие —
    хуже, чем не показать ничего).
    """
    employee = EmployeeRepository().get_employee(str(employee_id))
    if employee is None:
        return None
    position = str(getattr(employee, "position", "") or "").strip()
    if not is_master_position(position):
        return None
    raw_code = str(getattr(employee, "external_code", "") or "").strip()
    if not raw_code.isdigit():
        if raw_code:
            logger.warning(
                "Мастер %s: external_code=%r не число, привязка к Агбису невозможна",
                employee_id, raw_code,
            )
        return None
    return Master(
        employee_id=str(employee.id),
        name=(employee.full_name or employee.name or "").strip(),
        position=position,
        agbis_user_id=int(raw_code),
    )


def period_range(period: str, today: date | None = None) -> tuple[date, date]:
    """Границы периода ровно те же, что считает warmer.

    Импортируем его собственную функцию, а не повторяем логику: ключ кэша
    строится из этих дат, и разъехавшаяся на один день копия означала бы
    промах мимо прогретой записи и живой запрос в Firebird на каждое
    нажатие кнопки.
    """
    from app.services.fdb_cache import _period

    return _period(period, today or date.today())


class StaleCacheError(RuntimeError):
    """В кэше лежит отчёт, посчитанный до появления master_user_id."""


def _load_services(period: str) -> list[dict[str, Any]]:
    """Услуги из общего кэша masters.works за прогретый период.

    Записи, посчитанные до того, как в выборку добавили users.user_id, не
    содержат out_user_id — по ним фильтр «мои услуги» не даст ничего, и
    мастер увидел бы уверенный ноль вместо своих денег. Ключ кэша при этом
    не изменился, так что молча разойтись по форме они могут. Лучше
    признаться, что ответа пока нет, чем показать неправильный.
    """
    from app.services import fdb_cache

    df, dt = period_range(period)
    result = fdb_cache.get_or_compute("masters.works", (df, dt))
    services = list((result or {}).get("services") or [])
    if services and not any("out_user_id" in svc for svc in services):
        raise StaleCacheError(
            f"masters.works за {df}..{dt} посчитан без master_user_id"
        )
    return services


def _mine(services: Iterable[dict], master: Master, field: str) -> list[dict]:
    """Услуги, где в нужном скане (in/out) стоит именно этот мастер."""
    uid = master.agbis_user_id
    out = []
    for svc in services:
        raw = svc.get(field)
        if raw is None:
            continue
        try:
            if int(raw) == uid:
                out.append(svc)
        except (TypeError, ValueError):
            continue
    return out


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _advances(employee_id: str) -> float:
    try:
        return _num(PayoutRepository().advances_since_last_salary(employee_id)["total"])
    except Exception:
        logger.exception("Не удалось получить авансы для %s", employee_id)
        return 0.0


def get_earnings(master: Master, period: str = PERIOD_MONTH) -> dict[str, Any]:
    """Отчёт «мой заработок» за прогретый период.

    Для ученика начисление по проценту считается точно так же, но оно
    справочное: на руки идёт стипендия за дни присутствия. Обе цифры
    возвращаются, а что из них к выплате — решает поле `payout_basis`.
    """
    services = _mine(_load_services(period), master, "out_user_id")
    paid = [s for s in services if s.get("master_salary") is not None]

    accrued = round(sum(_num(s.get("master_salary")) for s in paid), 2)
    kredit = round(sum(_num(s.get("kredit")) for s in paid), 2)

    by_group: dict[str, dict[str, float]] = {}
    for svc in paid:
        group = str(svc.get("service_group") or "Другое")
        slot = by_group.setdefault(group, {"count": 0, "kredit": 0.0, "salary": 0.0})
        slot["count"] += 1
        slot["kredit"] += _num(svc.get("kredit"))
        slot["salary"] += _num(svc.get("master_salary"))
    groups = sorted(
        ({"group": g, **v} for g, v in by_group.items()),
        key=lambda r: r["salary"],
        reverse=True,
    )

    df, dt = period_range(period)
    advances = _advances(master.employee_id)
    report: dict[str, Any] = {
        "period": period,
        "period_label": PERIOD_LABELS.get(period, period),
        "date_from": df,
        "date_to": dt,
        "services_count": len(paid),
        "kredit": kredit,
        "accrued": accrued,
        "groups": groups,
        "advances": advances,
        "warnings_count": sum(1 for s in paid if s.get("warnings")),
        "is_apprentice": master.is_apprentice,
    }

    if master.is_apprentice:
        stipend, days = _apprentice_stipend(master, df, dt)
        report["stipend"] = stipend
        report["stipend_days"] = days
        report["day_rate"] = APPRENTICE_DAY_RATE
        report["payout_basis"] = "stipend"
        report["to_pay"] = round(stipend - advances, 2)
    else:
        report["payout_basis"] = "accrued"
        report["to_pay"] = round(accrued - advances, 2)
    return report


def _apprentice_stipend(master: Master, df: date, dt: date) -> tuple[float, int]:
    """Стипендия ученика за период: дни присутствия x дневная ставка."""
    from app.services.masters_service import get_apprentice_stipends

    try:
        for row in get_apprentice_stipends(df, dt):
            if str(row.get("employee_id")) == master.employee_id:
                return _num(row.get("stipend")), int(row.get("days_count") or 0)
    except Exception:
        logger.exception("Не удалось посчитать стипендию для %s", master.employee_id)
    return 0.0, 0


def get_wip(master: Master) -> list[dict[str, Any]]:
    """Услуги, принятые этим мастером и ещё не сданные.

    Склеиваем текущий и прошлый месяц: работа, принятая в конце прошлого
    месяца и до сих пор открытая, — ровно тот случай, ради которого экран
    и нужен, а одно месячное окно её бы не показало.

    Квартал был бы шире, но warmer его фактически не держит горячим
    (проверено на проде: запись пустая), и обращение к нему означало бы
    живой запрос на самом дорогом отчёте системы при каждом нажатии
    кнопки. Два прогретых месяца дают ~30-60 дней глубины бесплатно;
    работа, висящая дольше, — повод для разговора, а не для отчёта.
    """
    seen: set[Any] = set()
    services: list[dict] = []
    for period in (PERIOD_MONTH, PERIOD_PREV_MONTH):
        for svc in _mine(_load_services(period), master, "in_user_id"):
            key = svc.get("service_id")
            if key is not None and key in seen:
                continue
            if key is not None:
                seen.add(key)
            services.append(svc)
    today = date.today()
    wip = []
    for svc in services:
        if str(svc.get("status")) != "В работе":
            continue
        days = None
        raw_in = svc.get("in_time")
        if raw_in:
            try:
                days = (today - date.fromisoformat(str(raw_in)[:10])).days
            except ValueError:
                days = None
        wip.append({
            "doc_num": svc.get("doc_num"),
            "name": svc.get("name"),
            "service_group": svc.get("service_group"),
            "kredit": _num(svc.get("kredit")),
            "in_time": raw_in,
            "days": days,
            "urgent": str(svc.get("code") or "").startswith("144."),
        })
    wip.sort(key=lambda r: (not r["urgent"], -(r["days"] or 0)))
    return wip


def get_advance_cap(master: Master) -> dict[str, Any]:
    """Сколько мастер может попросить авансом прямо сейчас.

    Потолок — заработанное на сегодня минус уже взятое с последней
    зарплаты. Сейчас эту арифметику админ делает руками на каждый запрос.
    """
    report = get_earnings(master, PERIOD_MONTH)
    base = report["stipend"] if report["payout_basis"] == "stipend" else report["accrued"]
    return {
        "earned": base,
        "advances": report["advances"],
        "available": max(0.0, round(base - report["advances"], 2)),
        "basis": report["payout_basis"],
    }
