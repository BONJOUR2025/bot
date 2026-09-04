"""Картинка расписания (app/utils/image.py:create_schedule_image).

Проверяется не внешний вид, а раскладка и то, что рендер не падает на
данных, которые реально приходят из листа Excel: месяц может начинаться с
любого дня недели, длиться 28-31 день, в ячейке может стоять код филиала,
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


def _sheet(n_days: int, start: int, values: list[str], name: str = "Тест 0001"):
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


def _render(df, weekdays, name="Тест 0001", month="ТЕСТ"):
    path = img.create_schedule_image(df, name, month, weekdays)
    assert path and os.path.exists(path)
    with Image.open(path) as im:
        return im.size


class TestLayout:
    def test_width_comes_from_the_theme(self, in_tmp):
        """Ширина задана темой, а не разбросана по рендеру."""
        df, wd = _sheet(30, 0, ["Ц"] * 30)
        assert _render(df, wd)[0] == img.SCHEDULE_THEME["width"]

    def test_portrait_proportions_for_telegram(self, in_tmp):
        """Картинку смотрят с телефона: она должна быть вертикальной."""
        df, wd = _sheet(31, 6, ["Ц"] * 31)
        w, h = _render(df, wd)
        assert h > w

    @pytest.mark.parametrize("n_days, start, weeks", [
        (30, 0, 5),   # с понедельника
        (31, 1, 5),   # со вторника — сентябрь 2026
        (31, 6, 6),   # с воскресенья: шесть недель, самый высокий случай
        (28, 0, 4),   # февраль ровно в четыре недели
        (29, 5, 5),   # високосный февраль
        (28, 3, 5),
    ])
    def test_height_follows_the_number_of_weeks(self, in_tmp, n_days, start, weeks):
        df, wd = _sheet(n_days, start, [""] * n_days)
        h = _render(df, wd)[1]
        # Высота линейна по числу недель: шаг считаем по двум крайним
        # случаям, вместо того чтобы дублировать здесь арифметику раскладки.
        df4, wd4 = _sheet(28, 0, [""] * 28)
        df6, wd6 = _sheet(31, 6, [""] * 31)
        h4, h6 = _render(df4, wd4)[1], _render(df6, wd6)[1]
        step = (h6 - h4) / 2
        assert h == pytest.approx(h4 + step * (weeks - 4), abs=2)

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
        """Новый филиал заводят в справочнике раньше, чем в палитре здесь."""
        df, wd = _sheet(31, 0, ["Щ"] * 31)
        assert _render(df, wd)[0] == img.SCHEDULE_THEME["width"]

    def test_garbage_weekdays_do_not_crash(self, in_tmp):
        df, _ = _sheet(31, 0, ["А"] * 31)
        assert _render(df, ["?"] * 31)[0] == img.SCHEDULE_THEME["width"]

    def test_missing_employee_returns_none(self, in_tmp):
        df, wd = _sheet(30, 0, ["Ц"] * 30)
        assert img.create_schedule_image(df, "Никто", "ТЕСТ", wd) is None

    def test_name_is_matched_case_insensitively(self, in_tmp):
        df, wd = _sheet(30, 0, ["Ц"] * 30, name="Вера 0102")
        assert img.create_schedule_image(df, "вера 0102", "ТЕСТ", wd)

    def test_empty_month_renders_without_a_legend(self, in_tmp):
        df, wd = _sheet(31, 2, [""] * 31)
        assert _render(df, wd)[0] == img.SCHEDULE_THEME["width"]

    def test_short_weekday_list_is_tolerated(self, in_tmp):
        """weekdays приходит срезом [2:33] и бывает короче числа дней."""
        df, _ = _sheet(31, 0, ["М"] * 31)
        assert _render(df, WD * 2)[0] == img.SCHEDULE_THEME["width"]

    def test_a_very_long_name_does_not_widen_the_image(self, in_tmp):
        long_name = "Александра Константинопольская-Вишневецкая 9909"
        df, wd = _sheet(30, 1, ["Гп"] * 30, name=long_name)
        assert _render(df, wd, name=long_name)[0] == img.SCHEDULE_THEME["width"]

    def test_name_without_a_tab_number_renders(self, in_tmp):
        df, wd = _sheet(30, 0, ["Ц"] * 30, name="Вера")
        assert _render(df, wd, name="Вера")[0] == img.SCHEDULE_THEME["width"]


class TestTheme:
    def test_theme_holds_the_visual_tokens(self):
        """Цвета и размеры собраны в одном месте — иначе тёмную тему
        пришлось бы собирать по всему рендеру."""
        required = {"background", "surface", "border", "text", "text_secondary",
                    "accent", "accent_soft", "weekend", "radius_card", "width", "scale"}
        assert required <= set(img.SCHEDULE_THEME)

    def test_every_active_salon_has_a_full_palette(self):
        """У филиала должны быть все четыре роли, иначе карточка соберётся
        из цветов разных наборов."""
        try:
            from app.data.salon_repository import SalonRepository
            codes = {s.code for s in SalonRepository().list_salons(status="active") if s.code}
        except Exception:
            pytest.skip("справочник филиалов недоступен")
        for code in codes:
            pal = img.SALON_PALETTE.get(code)
            assert pal, f"нет палитры для кода {code}"
            assert {"primary", "bg", "border", "text"} <= set(pal)

    def test_primary_colours_are_distinct(self):
        values = [p["primary"] for p in img.SALON_PALETTE.values()]
        assert len(values) == len(set(values))

    def test_grand_palace_and_mercury_match_the_brief(self):
        """Фиолетовый и зелёный заданы макетом — они опорные для всей палитры."""
        assert img.SALON_PALETTE["Гп"]["primary"].upper() == "#7C4DFF"
        assert img.SALON_PALETTE["М"]["primary"].upper() == "#269B6B"


class TestHelpers:
    @pytest.mark.parametrize("raw, expected", [
        ("10:00-22:00", "10:00 – 22:00"),
        ("  11:00 - 21:00  ", "11:00 – 21:00"),
        ("", ""),
        ("круглосуточно", "круглосуточно"),
    ])
    def test_hours_label(self, raw, expected):
        assert img._hours_label({"weekday": raw, "weekend": ""}, False) == expected

    def test_weekend_hours_win_on_a_weekend(self):
        info = {"weekday": "10:00-22:00", "weekend": "11:00-20:00"}
        assert img._hours_label(info, True) == "11:00 – 20:00"
        assert img._hours_label(info, False) == "10:00 – 22:00"

    def test_weekend_falls_back_to_weekday_hours(self):
        info = {"weekday": "10:00-22:00", "weekend": ""}
        assert img._hours_label(info, True) == "10:00 – 22:00"

    @pytest.mark.parametrize("raw, expected", [
        ('ТЦ "Меркурий"', "ТЦ «Меркурий»"),
        ('ТЦ "Охта Молл"', "ТЦ «Охта Молл»"),
        ("Гранд Палас", "Гранд Палас"),
        ("", ""),
    ])
    def test_russian_quotes(self, raw, expected):
        assert img._ru_quotes(raw) == expected
