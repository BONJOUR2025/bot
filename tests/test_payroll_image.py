"""Картинка расчётного листа (app/utils/image.py:create_payroll_report_image).

Проверяется не внешний вид, а то, что читается по размеру и структуре
результата: карточка нулевых удержаний не рисуется, принудительный KPI не
получает полосу выполнения, отчёт собирается на неполных данных.

Формат входа — тот же, что возвращает generate_employee_report_from_payroll();
здесь он собирается теми же средствами, включая узкий неразрывный пробел в
суммах (U+202F): именно по нему разбираются план и факт, и обычный пробел
ломает разбор.
"""
from __future__ import annotations

import os

import pytest
from PIL import Image

from app.utils import image as img

NBSP = " "


def money(v: float) -> str:
    return f"{int(round(v)):,} ₽".replace(",", NBSP)


def kpi(rate: int, plan: float, fact: float, met: bool) -> str:
    head = f"{'✅' if met else '❌'} {rate}%, план {'выполнен' if met else 'не выполнен'}"
    detail = f"План: {money(plan)}  Факт: {money(fact)}"
    tail = (f"Перевыполнение: +{money(fact - plan)}" if met
            else f"До 80%: {money(plan * 0.8 - fact)}")
    return f"{head}\n{detail}\n{tail}"


def kpi_forced(rate: int, commission: float, fact: float, maximum: bool = True) -> str:
    return (f"⚙ Принудительно: {'макс.' if maximum else 'мин.'}\n"
            f"✅ {rate}%, комиссия: {money(commission)}\n"
            f"Факт: {money(fact)}")


def sections(kpi_rows=None, charges=None, deductions=None, name="Тест Тестов"):
    kpi_rows = kpi_rows if kpi_rows is not None else [
        ("Ремонт", kpi(7, 420000, 511300, True)),
        ("Косметика", kpi(4, 90000, 58400, False)),
    ]
    charges = charges if charges is not None else [
        ("Оклад", money(54800)), ("Ремонт", money(35791)),
        ("Косметика", money(2336)), ("Бонус", money(5000)),
    ]
    deductions = deductions if deductions is not None else [
        ("Удержание", money(1500)), ("Аванс", money(40000)),
    ]
    total = 97927
    held = sum(int("".join(c for c in v if c.isdigit())) for _, v in deductions)
    return [
        [("ЗАГОЛОВОК ОТЧЁТА", ""), ("Сотрудник", name), ("Период", "СЕНТЯБРЬ"),
         ("Основная ставка", money(2800)), ("Основные смены", "15"),
         ("Дополнительная ставка", money(3200)), ("Дополнительные смены", "4")],
        [("KPI", "")] + kpi_rows,
        [("НАЧИСЛЕНИЯ И УДЕРЖАНИЯ", "")] + charges
        + [("ИТОГО", money(total))] + deductions
        + [("К выплате", money(total - held))],
    ]


@pytest.fixture
def render(tmp_path):
    def _render(secs, stem="report"):
        path = img.create_payroll_report_image(secs, str(tmp_path / f"{stem}.png"))
        assert path and os.path.exists(path)
        with Image.open(path) as im:
            return im.size
    return _render


class TestShiftsWord:
    @pytest.mark.parametrize("n, word", [
        ("1", "смена"), ("2", "смены"), ("4", "смены"), ("5", "смен"),
        ("11", "смен"), ("14", "смен"), ("21", "смена"), ("22", "смены"),
        ("0", "смен"), ("100", "смен"), ("—", "смен"), ("", "смен"),
    ])
    def test_plural(self, n, word):
        assert img._shifts_word(n) == word


class TestLayout:
    def test_width_matches_the_schedule_image(self, render):
        """Обе картинки шлёт один бот — ширина у них общая."""
        assert render(sections())[0] == 560

    def test_zero_deductions_do_not_get_a_card(self, render):
        """«− 0 ₽» дважды подряд занимало карточку и ничего не сообщало."""
        zero = render(sections(deductions=[("Удержание", money(0)),
                                           ("Аванс", money(0))]), "zero")[1]
        real = render(sections(), "real")[1]
        assert zero < real

    def test_one_real_deduction_keeps_the_card(self, render):
        none_ = render(sections(deductions=[("Аванс", money(0))]), "none")[1]
        one = render(sections(deductions=[("Аванс", money(40000))]), "one")[1]
        assert one > none_

    def test_forced_kpi_is_shorter_than_a_measured_one(self, render):
        """У принудительного KPI нет полосы выполнения — сравнивать не с чем."""
        forced = render(sections(kpi_rows=[("Ремонт", kpi_forced(7, 35791, 511300))]), "f")[1]
        normal = render(sections(kpi_rows=[("Ремонт", kpi(7, 420000, 511300, True))]), "n")[1]
        assert forced < normal

    def test_kpi_without_a_plan_is_shorter_still(self, render):
        no_plan = render(sections(kpi_rows=[("Ремонт", "—")]), "np")[1]
        forced = render(sections(kpi_rows=[("Ремонт", kpi_forced(7, 35791, 511300))]), "f2")[1]
        assert no_plan < forced


class TestRobustness:
    def test_renders_without_a_kpi_section(self, render):
        secs = sections()
        assert render([secs[0], [("KPI", "")], secs[2]], "nokpi")[0] == 560

    def test_renders_with_only_a_header(self, render):
        assert render([sections()[0]], "hdr")[0] == 560

    def test_long_name_does_not_break_the_layout(self, render):
        long_name = "Александра Константинопольская-Вишневецкая"
        assert render(sections(name=long_name), "long")[0] == 560

    def test_ordinary_spaces_in_sums_do_not_crash(self, render):
        """Суммы приходят с U+202F, но лист могли собрать и обычным пробелом."""
        plain = ("✅ 7%, план выполнен\n"
                 "План: 420 000 ₽  Факт: 511 300 ₽\n"
                 "Перевыполнение: +91 300 ₽")
        assert render(sections(kpi_rows=[("Ремонт", plain)]), "plain")[0] == 560

    def test_missing_net_pay_still_renders(self, render):
        secs = sections()
        secs[2] = [row for row in secs[2] if row[0] != "К выплате"]
        assert render(secs, "nonet")[0] == 560
