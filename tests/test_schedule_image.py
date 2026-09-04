"""Картинка расписания (app/utils/image.py:create_schedule_image).

Проверяется не внешний вид, а раскладка и то, что функция не падает на
данных, которые реально приходят из листа Excel: месяц может начинаться с
любого дня недели, длиться 28-31 день, в ячейке может стоять код салона,
которого нет в палитре, а дни недели могут прийти мусором.

Отдельно закреплено число недель в сетке: именно оно определяет высоту
картинки, и ошибка на единицу срезала бы последние дни месяца.
"""
from __future__ import annotations

import os

import pandas as pd
import pytest
from PIL import Image

from app.utils import image as img

WD = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def _sheet(n_days: int, start: int, values: list[str], name: str = "Тест"):
    """Лист на одного сотрудника: (DataFrame, дни недели).

    start — индекс дня недели, на который приходится 1-е число.
    """
    cols = ["ИМЯ", "период"] + [str(i) for i in range(1, n_days + 1)]
    df = pd.DataFrame([[name, None] + values], columns=cols)
    weekdays = [WD[(start + i) % 7] for i in range(n_days)]
    return df, weekdays


@pytest.fixture
def in_tmp(tmp_path, monkeypatch):
    """Файл пишется в cwd — уводим его из репозитория."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _render(df, weekdays, name="Тест", month="ТЕСТ"):
    path = img.create_schedule_image(df, name, month, weekdays)
    assert path and os.path.exists(path)
    with Image.open(path) as im:
        return im.size


class TestLayout:
    def test_width_matches_the_payroll_report(self, in_tmp):
        """Обе картинки шлёт один бот — ширина у них общая."""
        df, wd = _sheet(30, 0, ["Ц"] * 30)
        assert _render(df, wd)[0] == 560

    @pytest.mark.parametrize("n_days, start, weeks", [
        (30, 0, 5),   # с понедельника
        (31, 1, 5),   # со вторника — сентябрь 2026
        (31, 6, 6),   # с воскресенья: шесть недель, самый высокий случай
        (28, 0, 4),   # февраль ровно в четыре недели
        (28, 3, 5),
    ])
    def test_height_follows_the_number_of_weeks(self, in_tmp, n_days, start, weeks):
        df, wd = _sheet(n_days, start, [""] * n_days)
        h = _render(df, wd)[1]
        # Высота линейна по числу недель: считаем шаг по двум крайним случаям
        # вместо того, чтобы дублировать здесь арифметику раскладки.
        df4, wd4 = _sheet(28, 0, [""] * 28)
        df6, wd6 = _sheet(31, 6, [""] * 31)
        h4, h6 = _render(df4, wd4)[1], _render(df6, wd6)[1]
        step = (h6 - h4) / 2
        assert h == pytest.approx(h4 + step * (weeks - 4), abs=1)

    def test_legend_adds_height_only_when_there_are_shifts(self, in_tmp):
        empty, wd = _sheet(30, 0, [""] * 30)
        worked, _ = _sheet(30, 0, ["Ц"] * 30)
        assert _render(worked, wd)[1] > _render(empty, wd)[1]

    def test_more_salons_make_a_taller_legend(self, in_tmp):
        one, wd = _sheet(28, 0, ["Ц"] * 28)
        many, _ = _sheet(28, 0, (["Ц", "А", "М", "Оз", "Ох", "Гп"] * 5)[:28])
        assert _render(many, wd)[1] > _render(one, wd)[1]


class TestRobustness:
    def test_unknown_salon_code_still_renders(self, in_tmp):
        """Новый салон заводят в справочнике раньше, чем в палитре здесь."""
        df, wd = _sheet(31, 0, ["Щ"] * 31)
        assert _render(df, wd)[0] == 560

    def test_garbage_weekdays_do_not_crash(self, in_tmp):
        df, _ = _sheet(31, 0, ["А"] * 31)
        assert _render(df, ["?"] * 31)[0] == 560

    def test_missing_employee_returns_none(self, in_tmp):
        df, wd = _sheet(30, 0, ["Ц"] * 30)
        assert img.create_schedule_image(df, "Никто", "ТЕСТ", wd) is None

    def test_name_is_matched_case_insensitively(self, in_tmp):
        df, wd = _sheet(30, 0, ["Ц"] * 30, name="Вера 0102")
        assert img.create_schedule_image(df, "вера 0102", "ТЕСТ", wd)

    def test_empty_month_renders_without_a_legend(self, in_tmp):
        df, wd = _sheet(31, 2, [""] * 31)
        assert _render(df, wd)[0] == 560

    def test_short_weekday_list_is_tolerated(self, in_tmp):
        """weekdays приходит срезом [2:33] и бывает короче числа дней."""
        df, _ = _sheet(31, 0, ["М"] * 31)
        assert _render(df, WD * 2)[0] == 560


class TestPalette:
    def test_every_active_salon_code_has_a_colour(self):
        """Салон без цвета рисуется дефолтным синим — не ошибка, но и не
        задумка: коды из справочника должны быть различимы между собой."""
        try:
            from app.data.salon_repository import SalonRepository
            codes = {s.code for s in SalonRepository().list_salons(status="active") if s.code}
        except Exception:
            pytest.skip("справочник салонов недоступен")
        missing = codes - set(img.SALON_COLORS)
        assert not missing, f"без цвета остались коды: {sorted(missing)}"

    def test_colours_are_distinct(self):
        values = list(img.SALON_COLORS.values())
        assert len(values) == len(set(values))
