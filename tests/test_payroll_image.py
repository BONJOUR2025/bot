"""Картинка расчётного листа (app/utils/image.py:create_payroll_report_image).

Проверяется не внешний вид, а то, что читается по размеру и структуре
результата: карточка удержаний схлопывается при нулях, принудительный KPI не
получает полосу выполнения, высота следует содержимому, лист собирается на
неполных данных.

Формат входа — тот же, что возвращает generate_employee_report_from_payroll();
здесь он собирается теми же средствами, включая узкий неразрывный пробел в
суммах (U+202F): именно по нему разбираются план и факт.
"""
from __future__ import annotations

import os

import pytest
from PIL import Image

from app.utils import image as img

NBSP = " "
W = img.PAYROLL_THEME["width"]


def money(v: float) -> str:
    return f"{int(round(v)):,} ₽".replace(",", NBSP)


def neg_money(v: float) -> str:
    return "−" + NBSP + money(v)


def kpi(rate: int, plan: float, fact: float, met: bool) -> str:
    head = f"{'✅' if met else '❌'} {rate}%, план {'выполнен' if met else 'не выполнен'}"
    detail = f"План: {money(plan)}  Факт: {money(fact)}"
    # Как в report.py: «перевыполнение» только когда факт реально выше плана,
    # иначе — процент выполнения.
    if met:
        tail = (f"Перевыполнение: +{money(fact - plan)}" if fact > plan
                else f"Выполнение: {int(round(fact / plan * 100))}%")
    else:
        tail = f"До 80%: {money(max(0.0, plan * 0.8 - fact))}"
    return f"{head}\n{detail}\n{tail}"


def kpi_forced(rate: int, commission: float, fact: float, maximum: bool = True) -> str:
    return (f"⚙ Принудительно: {'макс.' if maximum else 'мин.'}\n"
            f"✅ {rate}%, комиссия: {money(commission)}\n"
            f"Факт: {money(fact)}")


def sections(kpi_rows=None, charges=None, deductions=None,
             name="Екатерина 2201", total=None, net=None):
    kpi_rows = kpi_rows if kpi_rows is not None else [
        ("Ремонт", kpi(1, 823333, 31350, False)),
        ("Косметика", kpi(5, 69667, 5150, False)),
    ]
    charges = charges if charges is not None else [
        ("Оклад", money(65650)), ("Ремонт", money(314)),
        ("Косметика", money(258)), ("Обувь", money(0)), ("Бонус", money(0)),
    ]
    deductions = deductions if deductions is not None else [("Аванс", money(70000))]
    if total is None:
        total = sum(int("".join(c for c in v if c.isdigit())) for _, v in charges)
    held = sum(int("".join(c for c in v if c.isdigit()) or 0) for _, v in deductions)
    net_val = total - held if net is None else net
    net_str = (neg_money(abs(net_val)) if net_val < 0 else money(net_val))
    return [
        [("ЗАГОЛОВОК ОТЧЁТА", ""), ("Сотрудник", name), ("Период", "СЕНТЯБРЬ"),
         ("Основная ставка", money(3350)), ("Основные смены", "15"),
         ("Дополнительная ставка", money(3850)), ("Дополнительные смены", "4")],
        [("KPI", "")] + kpi_rows,
        [("НАЧИСЛЕНИЯ И УДЕРЖАНИЯ", "")] + charges
        + [("ИТОГО", money(total))] + deductions + [("К выплате", net_str)],
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


class TestScenarios:
    """Сценарии A-H из задания: ни один не должен ломать раскладку."""

    def test_a_negative_net_pay(self, render):
        assert render(sections(), "a")[0] == W

    def test_b_positive_net_pay(self, render):
        secs = sections(deductions=[("Аванс", money(10000))])
        assert render(secs, "b")[0] == W

    def test_c_no_deductions(self, render):
        secs = sections(deductions=[("Аванс", money(0)), ("Удержание", money(0))])
        assert render(secs, "c")[0] == W

    def test_d_several_deductions(self, render):
        secs = sections(deductions=[("Удержание", money(1500)),
                                    ("Аванс", money(40000))])
        assert render(secs, "d")[0] == W

    def test_e_many_charges(self, render):
        charges = [(f"Начисление {i}", money(1000 * i)) for i in range(1, 12)]
        assert render(sections(charges=charges), "e")[0] == W

    def test_f_many_kpi(self, render):
        rows = [(f"Показатель {i}", kpi(i, 100000 * i, 50000 * i, i % 2 == 0))
                for i in range(1, 7)]
        assert render(sections(kpi_rows=rows), "f")[0] == W

    def test_g_long_name(self, render):
        long_name = "Александра Константинопольская-Вишневецкая 9909"
        assert render(sections(name=long_name), "g")[0] == W

    def test_h_huge_sums(self, render):
        charges = [("Оклад", money(9_876_543_210)), ("Ремонт", money(1_234_567_890))]
        secs = sections(charges=charges, deductions=[("Аванс", money(5_000_000_000))])
        assert render(secs, "h")[0] == W


class TestLayout:
    def test_width_comes_from_the_theme(self, render):
        assert render(sections())[0] == W

    def test_portrait_proportions_for_telegram(self, render):
        w, h = render(sections())
        assert h > w

    def test_zero_deductions_collapse_the_card(self, render):
        """«− 0 ₽» отдельной строкой занимало карточку и ничего не сообщало."""
        zero = render(sections(deductions=[("Удержание", money(0)),
                                           ("Аванс", money(0))]), "zero")[1]
        two = render(sections(deductions=[("Удержание", money(1500)),
                                          ("Аванс", money(40000))]), "two")[1]
        assert zero < two

    def test_each_deduction_adds_a_row(self, render):
        one = render(sections(deductions=[("Аванс", money(40000))]), "one")[1]
        two = render(sections(deductions=[("Удержание", money(1500)),
                                          ("Аванс", money(40000))]), "two2")[1]
        assert two > one

    def test_more_charges_make_a_taller_card(self, render):
        few = render(sections(charges=[("Оклад", money(50000))]), "few")[1]
        many = render(sections(charges=[(f"Строка {i}", money(100 * i))
                                        for i in range(1, 10)]), "many")[1]
        assert many > few

    def test_forced_kpi_is_shorter_than_a_measured_one(self, render):
        """У принудительного KPI нет полосы выполнения — сравнивать не с чем."""
        forced = render(sections(kpi_rows=[("Ремонт", kpi_forced(7, 35791, 511300))]), "f1")[1]
        normal = render(sections(kpi_rows=[("Ремонт", kpi(7, 420000, 511300, True))]), "n1")[1]
        assert forced < normal

    def test_kpi_without_a_plan_is_shorter_still(self, render):
        no_plan = render(sections(kpi_rows=[("Ремонт", "—")]), "np")[1]
        forced = render(sections(kpi_rows=[("Ремонт", kpi_forced(7, 35791, 511300))]), "f2")[1]
        assert no_plan < forced


class TestRobustness:
    def test_renders_without_a_kpi_section(self, render):
        secs = sections()
        assert render([secs[0], [("KPI", "")], secs[2]], "nokpi")[0] == W

    def test_renders_with_only_a_header(self, render):
        assert render([sections()[0]], "hdr")[0] == W

    def test_ordinary_spaces_in_sums_do_not_crash(self, render):
        """Суммы приходят с U+202F, но лист могли собрать и обычным пробелом."""
        plain = ("✅ 7%, план выполнен\n"
                 "План: 420 000 ₽  Факт: 511 300 ₽\n"
                 "Перевыполнение: +91 300 ₽")
        assert render(sections(kpi_rows=[("Ремонт", plain)]), "plain")[0] == W

    def test_missing_net_pay_still_renders(self, render):
        secs = sections()
        secs[2] = [row for row in secs[2] if row[0] != "К выплате"]
        assert render(secs, "nonet")[0] == W

    def test_name_without_a_tab_number(self, render):
        assert render(sections(name="Екатерина"), "noname")[0] == W

    def test_long_charge_labels_do_not_collide_with_sums(self, render):
        charges = [("Компенсация за использование личного транспорта", money(12345))]
        assert render(sections(charges=charges), "longlabel")[0] == W


class TestTheme:
    def test_theme_holds_the_visual_tokens(self):
        """Цвета и размеры собраны в одном месте — иначе тёмную тему
        пришлось бы собирать по всему рендеру."""
        required = {"background", "surface", "border", "text", "text_secondary",
                    "primary", "primary_soft", "positive", "negative",
                    "negative_soft", "progress_track", "radius_card",
                    "page_pad", "card_pad", "gap", "width", "scale"}
        assert required <= set(img.PAYROLL_THEME)

    def test_shares_the_shell_with_the_schedule(self):
        """Один холст, один фон, одно скругление — две картинки одного бота."""
        for key in ("width", "scale", "background", "radius_card"):
            assert img.PAYROLL_THEME[key] == img.SCHEDULE_THEME[key]

    def test_accents_differ_from_the_schedule(self):
        """Акцент разный намеренно: документы должны различаться с одного взгляда."""
        assert img.PAYROLL_THEME["primary"] != img.SCHEDULE_THEME["accent"]


class TestHelpers:
    @pytest.mark.parametrize("raw, expected", [
        ("65 650 ₽", 65650), ("−" + NBSP + "70 000 ₽", 70000),
        ("0 ₽", 0), ("—", 0), ("", 0),
    ])
    def test_amount_value(self, raw, expected):
        assert img._amount_value(raw) == expected

    @pytest.mark.parametrize("raw, expected", [
        ("−" + NBSP + "3 779 ₽", True), ("-3 779 ₽", True),
        ("3 779 ₽", False), ("0 ₽", False), ("", False),
    ])
    def test_is_negative(self, raw, expected):
        assert img._is_negative(raw) is expected
