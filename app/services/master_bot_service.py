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
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
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
    # Старший мастер сам работает на постах цеха, поэтому ему нужен и свой
    # кабинет мастера (заработок, «В работе», скан), а не только «Цех».
    "Старший мастер",
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


def work_kind(svc: dict[str, Any]) -> str:
    """Вид работ для мастера — папка услуги в Агбисе без номера.

    Раньше вид определялся по коду услуги (GROUP_RULES в masters_service), и у
    мастера по сумкам больше половины работ падало в «Другое»: коды сумочного
    ремонта в правила не входят. Папки Агбиса («09. Ремонт чемоданов, сумок,
    саквояжей», «07. Ушивка, ремонт ремней») есть у каждой услуги и понятны
    без расшифровки.
    """
    folder = str(svc.get("folder_name") or "").strip()
    name = re.sub(r"^\d+(\.\d+)*\.?\s*", "", folder).strip()
    return name or str(svc.get("service_group") or "Другое")


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
        group = work_kind(svc)
        slot = by_group.setdefault(group, {"count": 0, "kredit": 0.0, "salary": 0.0})
        slot["count"] += 1
        slot["kredit"] += _num(svc.get("kredit"))
        slot["salary"] += _num(svc.get("master_salary"))
    groups = sorted(
        ({"group": g, **v} for g, v in by_group.items()),
        key=lambda r: r["salary"],
        reverse=True,
    )

    # Каждая услуга — для детальной сводки в кабинете (график по дням, фильтр
    # по видам работ, список), новые сверху. Ставка в отчёте masters.works не
    # сериализуется (salary_rate выкидывается перед отдачей), поэтому
    # считается обратно из суммы работ и начисления.
    service_rows = sorted(
        (
            {
                "doc_num": svc.get("doc_num"),
                "name": svc.get("name"),
                "service_group": work_kind(svc),
                "kredit": _num(svc.get("kredit")),
                "salary": _num(svc.get("master_salary")),
                "rate": (
                    round(_num(svc.get("master_salary")) / _num(svc.get("kredit")), 4)
                    if _num(svc.get("kredit"))
                    else None
                ),
                "in_time": svc.get("in_time"),
                "out_time": svc.get("out_time"),
                "day": str(svc.get("out_time"))[:10] if svc.get("out_time") else None,
                "duration_min": svc.get("duration_min"),
            }
            for svc in paid
        ),
        key=lambda row: row["out_time"] or "",
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
        "services": service_rows,
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


# Сколько «В работе» живёт в памяти процесса. Экран открывают пачками —
# посмотрел, отсканировал, вернулся, — и каждый заход стоил бы запроса в
# Агбис за сроками, фото и комментариями. Полторы минуты достаточно, чтобы
# переключение вкладок было мгновенным, и мало, чтобы только что сданная
# работа задержалась на экране; кнопка «Обновить» кэш всё равно обходит.
WIP_CACHE_TTL_SECONDS = 90
_wip_cache: dict[int, tuple[float, list[dict[str, Any]]]] = {}


def get_wip(master: Master, *, refresh: bool = False) -> list[dict[str, Any]]:
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
    import time as _time

    if not refresh:
        cached = _wip_cache.get(master.agbis_user_id)
        if cached and _time.monotonic() - cached[0] < WIP_CACHE_TTL_SECONDS:
            return cached[1]
    rows = _build_wip(master)
    _wip_cache[master.agbis_user_id] = (_time.monotonic(), rows)
    return rows


def invalidate_wip(master_user_id: int | None = None) -> None:
    """Сбросить кэш «В работе» — после скана, который меняет этот список."""
    if master_user_id is None:
        _wip_cache.clear()
    else:
        _wip_cache.pop(int(master_user_id), None)


def _build_wip(master: Master) -> list[dict[str, Any]]:
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
    open_services = [svc for svc in services if str(svc.get("status")) == "В работе"]
    details = _order_details([svc.get("service_id") for svc in open_services])
    for svc in open_services:
        days = None
        raw_in = svc.get("in_time")
        if raw_in:
            try:
                days = (today - date.fromisoformat(str(raw_in)[:10])).days
            except ValueError:
                days = None
        extra = details.get(svc.get("service_id")) or {}
        wip.append({
            "service_id": svc.get("service_id"),
            "doc_num": svc.get("doc_num"),
            "name": svc.get("name"),
            "service_group": svc.get("service_group"),
            "kredit": _num(svc.get("kredit")),
            "in_time": raw_in,
            "days": days,
            "urgent": str(svc.get("code") or "").startswith("144."),
            **deadline(extra.get("due"), datetime.now()),
            "photos": extra.get("photos") or [],
            "comments": extra.get("comments") or [],
        })
    wip.sort(key=_wip_order)
    return wip


# Порядок в «В работе»: сначала то, что уже горит, потом срочные, потом
# завтрашние, дальше — кто дольше ждёт.
_DUE_RANK = {"overdue": 0, "today": 1, "tomorrow": 3}


def _wip_order(row: dict[str, Any]) -> tuple:
    rank = _DUE_RANK.get(row.get("due_state"), 4)
    if rank > 1 and row.get("urgent"):
        rank = 2
    # Просроченные — самые давние сверху; сегодняшние — по часу обещания.
    return (rank, -(row.get("overdue_days") or 0), row.get("due") or "", -(row.get("days") or 0))


def deadline(due: Optional[datetime], now: datetime) -> dict[str, Any]:
    """Где обещанная клиенту дата относительно «сейчас».

    Обещание — DOCS_ORDER.DATE_OUT, тот же срок, по которому считаются
    просрочки. Просрочен — если момент уже прошёл (а не только день): заказ,
    обещанный сегодня к 12:00, в 15:00 уже просрочен.
    """
    if due is None:
        return {"due": None, "due_state": None, "overdue_days": None}
    state = None
    overdue_days = None
    if due < now:
        state = "overdue"
        overdue_days = max((now.date() - due.date()).days, 0)
    elif due.date() == now.date():
        state = "today"
    elif due.date() == now.date() + timedelta(days=1):
        state = "tomorrow"
    return {"due": due.isoformat(timespec="minutes"), "due_state": state, "overdue_days": overdue_days}


# Сколько снимков изделия отдавать в «В работе». Миниатюра (~3 КБ) едет прямо
# в ответе только у первого, главного: в списке видна она одна, а остальные
# просмотрщик всё равно грузит в полном размере. С миниатюрами у всех шести
# экран Корягина весил 259 КБ.
WIP_PHOTOS_PER_ITEM = 6


def _text(value: Any) -> str:
    """Строка из Агбиса: соединение открыто с charset=NONE, поэтому текст
    приходит байтами в cp1251."""
    if isinstance(value, bytes):
        return value.decode("cp1251", "replace").strip()
    return str(value or "").strip()


def _order_details(service_ids: list[Any], with_photos: bool = True) -> dict[Any, dict[str, Any]]:
    """Срок заказа, фото изделия и комментарии приёмщика — живым запросом в Агбис.

    Срок — DOCS_ORDER.DATE_OUT. В кэше отчёта masters.works его нет, а тащить
    туда ради одного экрана значило бы менять самый дорогой отчёт системы.

    Комментарий приёмщик пишет в «дополнение» услуги типа «КОММЕНТАРИЙ!» —
    ADDON_ORDER_SERVICES.VALUE_STR (заказ 37441-7, «Профилактика женская»:
    «вибрам черный»). Это основное место: почти пять тысяч заполнений на
    свежих заказах против пары сотен у EXT_INFO. Берём и остальные дополнения
    со свободным вводом («ЦВЕТ ТОНИРОВКИ/ПОКРАСКИ», «Какой вид материала»,
    «Дополнительный комментарий пошива») — они подписаны названием типа;
    справочные дополнения (цвет, материал, дефекты — is_combo = 1) это не
    комментарии, а характеристики, и мастеру в список не идут. «Фамилия
    клиента» исключена намеренно: мастеру она не нужна.

    VALUE_STR обязательно читать через CAST(... CHARACTER SET OCTETS):
    соединение открыто в UTF8, а в колонке лежит cp1251, и без приведения fdb
    падает на UnicodeDecodeError — вместе с ним пропали бы и сроки, и фото.

    Плюс EXT_INFO услуги и её изделия («согласовать цвет», «+ ПЫЛЬНИК») и
    почти неиспользуемая DOC_ORDER_SERV_COMMENTS (73 строки за всю историю):
    мастер не должен пропустить «в понедельник клиент улетает в 16.00» из-за
    того, что приёмщик написал не в то поле. Помечаем, к чему относится
    запись: у изделия это замечание ко всей паре, у услуги — к конкретной
    работе. Пустой случай экран проговаривает явно.

    Фото в Агбисе всегда висит на изделии («Ботильоны»), а не на услуге
    («Набойки»): услуга ссылается на своё изделие через PARENT_DOS_ID. Строка
    без родителя сама и есть изделие. Миниатюра (DOC_ORDER_SERV_PHOTOS.SMALL)
    приходит data URI в том же ответе — отдельный запрос на каждую картинку
    это параллельные подключения к Firebird, которые однажды уже уронили
    сервер. Главное фото — первым.

    Всё по первичным ключам и индексам — миллисекунды. Если Агбис не ответил,
    экран всё равно показывается, просто без сроков и фото.
    """
    import base64

    ids = [int(i) for i in service_ids if i is not None]
    if not ids:
        return {}
    try:
        from app.services.firebird_service import _connect

        con = _connect()
        try:
            cur = con.cursor()
            out: dict[Any, dict[str, Any]] = {}
            item_of: dict[int, int] = {}
            for start in range(0, len(ids), 500):
                chunk = ids[start:start + 500]
                cur.execute(
                    "SELECT dos.id, dos.parent_dos_id, dor.date_out, dos.ext_info, dor.status_id "
                    "FROM doc_order_services dos "
                    "JOIN docs_order dor ON dor.id = dos.doc_order_id "
                    f"WHERE dos.id IN ({','.join('?' * len(chunk))})",
                    chunk,
                )
                for sid, parent_id, date_out, ext_info, order_status in cur.fetchall():
                    due = date_out if isinstance(date_out, datetime) and date_out.year > 2000 else None
                    comments = []
                    note = _text(ext_info)
                    if note:
                        comments.append({"text": note, "about": "услуге", "label": None})
                    out[sid] = {"due": due, "photos": [], "comments": comments,
                                "order_status_id": order_status}
                    item_of[sid] = parent_id or sid

            photos_of_item: dict[int, list[dict[str, Any]]] = {}
            note_of_item: dict[int, str] = {}
            items = sorted(set(item_of.values()))
            for start in range(0, len(items), 500):
                chunk = items[start:start + 500]
                cur.execute(
                    "SELECT dos.id, dos.ext_info FROM doc_order_services dos "
                    f"WHERE dos.id IN ({','.join('?' * len(chunk))})",
                    chunk,
                )
                for item_id, ext_info in cur.fetchall():
                    note = _text(ext_info)
                    if note:
                        note_of_item[item_id] = note
                if not with_photos:
                    # Обзор цеха (workshop_service) фото не показывает, а
                    # миниатюры сотни изделий — это мегабайты в одном ответе.
                    continue
                cur.execute(
                    "SELECT p.dos_id, p.id, p.md5_checksum, p.small FROM doc_order_serv_photos p "
                    f"WHERE p.dos_id IN ({','.join('?' * len(chunk))}) "
                    "ORDER BY p.dos_id, p.is_main_photo DESC, p.id",
                    chunk,
                )
                for item_id, photo_id, md5, small in cur.fetchall():
                    bucket = photos_of_item.setdefault(item_id, [])
                    if len(bucket) >= WIP_PHOTOS_PER_ITEM:
                        continue
                    if isinstance(md5, bytes):
                        md5 = md5.decode("ascii", "replace")
                    photo = {"id": photo_id, "md5": (md5 or "").strip(), "thumb": None}
                    if not bucket:
                        raw = small.read() if hasattr(small, "read") else small
                        if raw:
                            mime = "image/png" if raw[:4] == b"\x89PNG" else "image/jpeg"
                            photo["thumb"] = f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
                    bucket.append(photo)

            typed: dict[int, list[dict[str, Any]]] = {}
            rows = sorted(set(ids) | set(items))

            # Главное место комментария — «дополнение» услуги со свободным
            # вводом. Тип «КОММЕНТАРИЙ!» показываем без подписи, остальные —
            # с названием типа, иначе «в тон» непонятно само по себе.
            for start in range(0, len(rows), 500):
                chunk = rows[start:start + 500]
                cur.execute(
                    "SELECT a.line_id, "
                    "       CAST(t.descr AS VARCHAR(128) CHARACTER SET OCTETS), "
                    "       CAST(a.value_str AS VARCHAR(1024) CHARACTER SET OCTETS) "
                    "FROM addon_order_services a "
                    "  JOIN addon_types t ON t.id = a.addon_type_id "
                    f"WHERE a.line_id IN ({','.join('?' * len(chunk))}) "
                    "  AND (t.is_combo = 0 OR t.is_combo IS NULL) "
                    "  AND t.is_active = 1 AND t.value_type = 1 "
                    "ORDER BY a.line_id, a.num",
                    chunk,
                )
                for line_id, descr, value in cur.fetchall():
                    text = _text(value)
                    label = _text(descr).strip("!").strip()
                    if not text or "Фамилия клиента" in label:
                        continue
                    typed.setdefault(line_id, []).append({
                        "text": text,
                        "about": "услуге" if line_id in out else "изделию",
                        "label": None if label.upper() == "КОММЕНТАРИЙ" else label,
                    })

            # Редкая таблица отдельных комментариев — по строке услуги и по
            # строке изделия сразу.
            for start in range(0, len(rows), 500):
                chunk = rows[start:start + 500]
                cur.execute(
                    "SELECT c.dos_id, c.dt, c.comment FROM doc_order_serv_comments c "
                    f"WHERE c.dos_id IN ({','.join('?' * len(chunk))}) ORDER BY c.dt",
                    chunk,
                )
                for dos_id, when, comment in cur.fetchall():
                    text = _text(comment)
                    if not text:
                        continue
                    typed.setdefault(dos_id, []).append({
                        "text": text,
                        "about": "услуге" if dos_id in out else "изделию",
                        "label": None,
                        "date": when.isoformat(timespec="minutes") if isinstance(when, datetime) else None,
                    })

            for sid, item_id in item_of.items():
                out[sid]["photos"] = photos_of_item.get(item_id, [])
                note = note_of_item.get(item_id)
                extra = [{"text": note, "about": "изделию", "label": None}] if note and item_id != sid else []
                extra += typed.get(sid, []) + (typed.get(item_id, []) if item_id != sid else [])
                # Одно и то же замечание часто стоит и на изделии, и на услуге —
                # мастеру это один комментарий, а не два.
                seen_text = {c["text"] for c in out[sid]["comments"]}
                for comment in extra:
                    if comment["text"] in seen_text:
                        continue
                    seen_text.add(comment["text"])
                    out[sid]["comments"].append(comment)
            return out
        finally:
            con.close()
    except Exception:
        logger.exception("Не удалось получить сроки, фото и комментарии заказов для «В работе»")
        return {}


def master_can_see_photo(master_user_id: int, photo_id: int, md5: str) -> bool:
    """Снимок существует с этим хешем и снят с изделия, по услуге которого у
    мастера есть отметка. Чужие заказы мастеру не открываются."""
    from app.services.firebird_service import _connect

    con = _connect()
    try:
        cur = con.cursor()
        cur.execute(
            # Два EXISTS вместо одного с OR: так каждый идёт по своему индексу.
            "SELECT p.md5_checksum FROM doc_order_serv_photos p "
            "WHERE p.id = ? AND (EXISTS ("
            "  SELECT 1 FROM doc_order_services dos "
            "    JOIN user_session_actions usa ON usa.doc_order_services_id = dos.id "
            "    JOIN user_session us ON us.id = usa.user_session_id "
            "  WHERE dos.parent_dos_id = p.dos_id AND us.user_id = ?"
            ") OR EXISTS ("
            "  SELECT 1 FROM user_session_actions usa "
            "    JOIN user_session us ON us.id = usa.user_session_id "
            "  WHERE usa.doc_order_services_id = p.dos_id AND us.user_id = ?))",
            (photo_id, master_user_id, master_user_id),
        )
        row = cur.fetchone()
    finally:
        con.close()
    stored = row[0] if row else None
    if isinstance(stored, bytes):
        stored = stored.decode("ascii", "replace")
    return bool(stored) and stored.strip().upper() == (md5 or "").strip().upper()


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
