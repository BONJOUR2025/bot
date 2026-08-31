"""Рабочее окно: в какие дни и часы разрешено то или иное действие.

Вынесено из candidate_hours, когда понадобилось второе такое окно — для
звонков (call_hours). Механизм расчёта окна один на всех, различаются только
имена ключей в config.json и значения по умолчанию, поэтому расписание стало
объектом `Schedule`, а candidate_hours и call_hours — двумя его настройками.

Не путать с work_hours.py: тот отвечает за часы АВТОМАТИЗАЦИИ (ключи
automation_work_*, часовой пояс Москвы, weekday 0–6) и живёт своей жизнью с
времён телеграм-интервью. Здесь — окна, которые задаются днями недели 1–7 и
считаются по локальному времени сервера.

Время считается по ЛОКАЛЬНОМУ времени сервера, а не по UTC: оператор задаёт
часы в том виде, в каком видит их на часах. Это же локальное время — граница
календарного дня для правила «одна исходящая попытка в день»
(см. app/services/call_queue.py).

Выключенное расписание разрешает всё: пока оператор его не задал, поведение
ровно прежнее.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

log = logging.getLogger(__name__)

# Смещение локального времени приложения относительно UTC. Единственное место,
# где оно задано: и окна, и граница календарного дня в call_queue считают
# локальное время через to_local(), поэтому разъехаться им негде.
LOCAL_UTC_OFFSET = timedelta(hours=3)


def to_local(dt: datetime | None) -> datetime | None:
    """UTC-время из БД → локальное. Наивные datetime в этом проекте всегда
    UTC (datetime.utcnow), а показываем и сравниваем мы по локальным часам."""
    if dt is None:
        return None
    return dt + LOCAL_UTC_OFFSET


def local_now() -> datetime:
    """Текущее локальное время. Отдельная функция, чтобы тесты подменяли
    «сейчас» одним аргументом, а не патчили datetime глобально."""
    return datetime.utcnow() + LOCAL_UTC_OFFSET


def _parse_time(raw: str | None, fallback: str) -> time:
    for value in (raw, fallback):
        text = str(value or "").strip()
        if not text:
            continue
        try:
            hh, mm = text.split(":")[:2]
            return time(int(hh), int(mm))
        except Exception:
            continue
    return time(0, 0)


@dataclass(frozen=True)
class Schedule:
    """Одно именованное расписание: набор ключей конфига + значения по умолчанию."""

    key_enabled: str
    key_days: str
    key_start: str
    key_end: str
    default_days: tuple[int, ...] = (1, 2, 3, 4, 5)
    default_start: str = "09:00"
    default_end: str = "20:00"

    # ── чтение настроек ──────────────────────────────────────────────────
    def load(self, cfg: dict | None = None) -> dict:
        """{enabled, days, start, end} — нормализованное расписание."""
        if cfg is None:
            from app.services.config_service import ConfigService

            cfg = ConfigService().load()

        raw_days = cfg.get(self.key_days)
        if isinstance(raw_days, str):
            raw_days = [d for d in raw_days.replace(" ", "").split(",") if d]
        days: list[int] = []
        for d in raw_days if isinstance(raw_days, (list, tuple)) else []:
            try:
                n = int(d)
            except Exception:
                continue
            if 1 <= n <= 7:
                days.append(n)
        days = sorted(set(days)) or list(self.default_days)

        return {
            "enabled": bool(cfg.get(self.key_enabled)),
            "days": days,
            "start": str(cfg.get(self.key_start) or self.default_start),
            "end": str(cfg.get(self.key_end) or self.default_end),
        }

    # ── проверки ─────────────────────────────────────────────────────────
    def is_within(self, now: datetime | None = None, cfg: dict | None = None) -> bool:
        """Разрешено ли действие прямо сейчас."""
        schedule = self.load(cfg)
        if not schedule["enabled"]:
            return True  # расписание не настроено — прежнее поведение

        now = now or local_now()
        if now.isoweekday() not in schedule["days"]:
            return False

        start = _parse_time(schedule["start"], self.default_start)
        end = _parse_time(schedule["end"], self.default_end)
        current = now.time()
        if start <= end:
            return start <= current <= end
        # Окно через полночь (например 20:00–02:00): день начала считается рабочим.
        return current >= start or current <= end

    def next_window_start(
        self, now: datetime | None = None, cfg: dict | None = None
    ) -> datetime | None:
        """Когда откроется ближайшее окно. None — если оно уже открыто или
        расписание выключено. Нужен для показа оператору."""
        schedule = self.load(cfg)
        if not schedule["enabled"]:
            return None
        now = now or local_now()
        if self.is_within(now, cfg):
            return None
        return self.window_start_on_or_after(now, cfg=cfg)

    def window_start_on_or_after(
        self, moment: datetime | date, cfg: dict | None = None
    ) -> datetime | None:
        """Начало ближайшего окна в момент `moment` или позже.

        Ищем в пределах восьми дней: список дней недельный по определению,
        и если за неделю подходящего дня нет — его нет вовсе.
        """
        schedule = self.load(cfg)
        if not schedule["enabled"]:
            return moment if isinstance(moment, datetime) else datetime.combine(moment, time(0, 0))

        start = _parse_time(schedule["start"], self.default_start)
        if isinstance(moment, datetime):
            floor = moment
            first_day = moment.date()
        else:
            floor = datetime.combine(moment, time(0, 0))
            first_day = moment

        for offset in range(0, 8):
            day = first_day + timedelta(days=offset)
            if day.isoweekday() not in schedule["days"]:
                continue
            candidate = datetime.combine(day, start)
            if candidate >= floor:
                return candidate
        return None

    def shift_into_window(self, moment: datetime, cfg: dict | None = None) -> datetime:
        """Сдвинуть момент в ближайшее допустимое окно.

        Если момент уже внутри окна — возвращается как есть. Иначе — начало
        ближайшего окна на эту дату или позже. Выключенное расписание момент
        не меняет.
        """
        schedule = self.load(cfg)
        if not schedule["enabled"]:
            return moment
        if self.is_within(moment, cfg):
            return moment
        shifted = self.window_start_on_or_after(moment, cfg=cfg)
        return shifted or moment
