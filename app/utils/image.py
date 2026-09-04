from PIL import Image, ImageDraw, ImageFilter, ImageFont
import pandas as pd
import os
import re
from .logger import log

COLORS = {
    "П": "#ADD8E6",  # голубой
    "Ц": "#8A2BE2",  # фиолетовый
    "А": "#FFFF00",  # желтый
    "М": "#008000",  # зеленый
    "Р": "#D2B48C",  # светло коричневый
    "Оз": "#FFA500",  # рыжий
    "Ох": "#0000FF",  # синий
    "сб": "#FF0000",  # красный (специально для "сб")
    "вс": "#FF0000",  # красный (специально для "вс")
    "default": "#FFFFFF",  # белый
}


def _try_font(path: str, size: int):
    """Try to load a font, return None on failure."""
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return None


def _load_fonts():
    """Load fonts with Cyrillic support. Tries common paths for Windows and Linux."""
    size_regular = 16
    size_header = 17

    # Ordered preference: Windows system fonts first (PIL resolves them automatically),
    # then absolute Linux paths. Each entry is tried via ImageFont.truetype directly.
    # Priority: fonts that support both Cyrillic AND ₽ (ruble sign U+20BD)
    # Arial (Windows auto-resolved by PIL) and DejaVu both have full support.
    # Liberation Sans lacks the ₽ glyph, so it comes last.
    regular_candidates = [
        "arial.ttf",          # Windows: PIL resolves automatically from system fonts
        "calibri.ttf",        # Windows fallback
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    bold_candidates = [
        "arialbd.ttf",        # Windows bold Arial
        "calibrib.ttf",       # Windows bold Calibri
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]

    font_regular = None
    for path in regular_candidates:
        font_regular = _try_font(path, size_regular)
        if font_regular:
            log(f"Font regular: {path}")
            break

    font_bold = None
    for path in bold_candidates:
        font_bold = _try_font(path, size_regular)
        if font_bold:
            log(f"Font bold: {path}")
            break

    font_header = None
    for path in bold_candidates:
        font_header = _try_font(path, size_header)
        if font_header:
            break

    # Ultimate fallback (no Cyrillic, but at least won't crash)
    if not font_regular:
        font_regular = ImageFont.load_default()
    if not font_bold:
        font_bold = font_regular
    if not font_header:
        font_header = font_regular

    font_small = _try_font("arial.ttf", 13) or font_regular

    return font_regular, font_bold, font_header, font_small


# Highlighted rows (key names that get special treatment)
_HIGHLIGHT_TOTAL = {"ИТОГО"}
_HIGHLIGHT_NET = {"К выплате"}
_HIGHLIGHT_DEDUCT = {"Удержание", "Аванс"}

# Design constants
_BG = "#F5F7FA"
_CARD_BG = "#FFFFFF"
_SEC_HEADER_BG = "#1E3A5F"
_SEC_HEADER_TEXT = "#FFFFFF"
_ROW_ALT = "#EEF4FF"
_ROW_TOTAL = "#FFF8E1"
_ROW_NET = "#E8F5E9"
_ROW_DEDUCT = "#FFF0F0"
_KEY_COLOR = "#555566"
_VAL_COLOR = "#1A1A2E"
_VAL_TOTAL = "#E65100"
_VAL_NET = "#2E7D32"
_VAL_DEDUCT = "#C62828"
_BORDER = "#C8D0DC"
_SIDE_PAD = 24
_ROW_H = 38
_SEC_H = 44
_TABLE_GAP = 16
_BOTTOM_PAD = 24


def create_combined_table_image(tables, filename="salary_report.png"):
    """
    Generates a styled salary report image with proper height calculation.
    """
    if not tables or all(len(table) < 2 for table in tables):
        log("❌ Error: Empty list of tables provided!")
        return None

    font_regular, font_bold, font_header, font_small = _load_fonts()

    # --- measure column widths ---
    dummy_img = Image.new("RGB", (1, 1))
    dummy_draw = ImageDraw.Draw(dummy_img)

    max_key_w = 0
    max_val_w = 0
    for table in tables:
        for row in table[1:]:
            if len(row) != 2:
                continue
            key, value = row
            kw = dummy_draw.textlength(key, font=font_regular)
            if kw > max_key_w:
                max_key_w = kw
            for line in value.split("\n"):
                vw = dummy_draw.textlength(line, font=font_bold)
                if vw > max_val_w:
                    max_val_w = vw

    max_key_w = max(int(max_key_w) + 8, 120)
    max_val_w = max(int(max_val_w) + 8, 120)

    img_width = _SIDE_PAD + max_key_w + 16 + max_val_w + _SIDE_PAD
    img_width = max(img_width, 420)

    # --- calculate exact total height ---
    total_height = _SIDE_PAD  # top padding
    for table in tables:
        total_height += _SEC_H  # section header
        for row in table[1:]:
            if len(row) != 2:
                continue
            lines = row[1].split("\n")
            total_height += _ROW_H * len(lines)
        total_height += _TABLE_GAP  # gap after table
    total_height += _BOTTOM_PAD  # bottom padding

    log(f"Размеры изображения: ширина={img_width}, высота={total_height}")

    img = Image.new("RGB", (img_width, total_height), _BG)
    draw = ImageDraw.Draw(img)

    y = _SIDE_PAD

    for table in tables:
        section_title = table[0][0]

        # Section header bar
        draw.rectangle(
            [(0, y), (img_width, y + _SEC_H)],
            fill=_SEC_HEADER_BG,
        )
        title_w = draw.textlength(section_title, font=font_header)
        draw.text(
            ((img_width - title_w) / 2, y + (_SEC_H - 17) // 2),
            section_title,
            fill=_SEC_HEADER_TEXT,
            font=font_header,
        )
        y += _SEC_H

        # Card background behind all rows
        rows_data = [r for r in table[1:] if len(r) == 2]
        total_rows_h = sum(_ROW_H * len(r[1].split("\n")) for r in rows_data)
        draw.rectangle(
            [(0, y), (img_width, y + total_rows_h)],
            fill=_CARD_BG,
        )

        row_idx = 0
        for row in table[1:]:
            if len(row) != 2:
                continue
            key, value = row
            value_lines = value.split("\n")
            row_total_h = _ROW_H * len(value_lines)

            # Row background
            if key in _HIGHLIGHT_NET:
                row_bg = _ROW_NET
            elif key in _HIGHLIGHT_TOTAL:
                row_bg = _ROW_TOTAL
            elif key in _HIGHLIGHT_DEDUCT:
                row_bg = _ROW_DEDUCT
            elif row_idx % 2 == 1:
                row_bg = _ROW_ALT
            else:
                row_bg = _CARD_BG

            draw.rectangle([(0, y), (img_width, y + row_total_h)], fill=row_bg)

            # Separator line
            draw.line([(0, y), (img_width, y)], fill=_BORDER, width=1)

            # Key (right-aligned in key column)
            key_w = draw.textlength(key, font=font_regular)
            key_x = _SIDE_PAD + max_key_w - key_w
            key_y = y + (_ROW_H - 16) // 2
            draw.text((key_x, key_y), key, fill=_KEY_COLOR, font=font_regular)

            # Value (left-aligned, bold, colored by row type)
            if key in _HIGHLIGHT_NET:
                val_color = _VAL_NET
                val_font = font_bold
            elif key in _HIGHLIGHT_TOTAL:
                val_color = _VAL_TOTAL
                val_font = font_bold
            elif key in _HIGHLIGHT_DEDUCT:
                val_color = _VAL_DEDUCT
                val_font = font_regular
            else:
                val_color = _VAL_COLOR
                val_font = font_regular

            val_x = _SIDE_PAD + max_key_w + 16
            for i, line in enumerate(value_lines):
                line_y = y + (_ROW_H - 16) // 2 + i * _ROW_H
                draw.text((val_x, line_y), line, fill=val_color, font=val_font)

            y += row_total_h
            row_idx += 1

        # Bottom border of section
        draw.line([(0, y), (img_width, y)], fill=_BORDER, width=1)
        y += _TABLE_GAP

    img.save(filename)
    return filename


def _shifts_word(n: str) -> str:
    """«15 смен», «4 смены», «1 смена» — падеж по числу."""
    try:
        v = abs(int(str(n).strip()))
    except (TypeError, ValueError):
        return "смен"
    if 11 <= v % 100 <= 14:
        return "смен"
    return {1: "смена", 2: "смены", 3: "смены", 4: "смены"}.get(v % 10, "смен")


def create_payroll_report_image(sections: list, filename: str = "salary_report.png"):
    """Расчётный лист сотрудника картинкой (источник — SQL/Firebird).

    Ожидает структуру, которую возвращает generate_employee_report_from_payroll().

    Порядок блоков отвечает вопросу, ради которого лист и открывают: сколько
    я получу. Поэтому сумма к выплате стоит первой и крупно, а KPI — в конце:
    он не ответ, а объяснение, откуда взялся ответ. Раньше было наоборот, и
    до главного числа приходилось долистывать картинку до низа.
    """
    # ── палитра ───────────────────────────────────────────────────────
    BG = "#F0F2F8"; CARD = "#FFFFFF"; ACCENT = "#4A6CF7"
    # Согласовано с расписанием (SALON_COLORS): один уровень насыщенности,
    # чтобы две картинки от одного бота читались как одна система.
    GREEN = "#1F8A5B"; WARN = "#C2701A"; RED = "#C0453A"
    TEXT = "#1A1A2E"; SUBTEXT = "#6B6B8A"; BORDER = "#DDE0EE"; PBAR_BG = "#E4E6F0"

    W = 560; PAD = 18; IX = PAD + 14

    regular_candidates = [
        "arial.ttf", "calibri.ttf",
        "C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/calibri.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    bold_candidates = [
        "arialbd.ttf", "calibrib.ttf",
        "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/calibrib.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]

    def tf(paths, size):
        for p in paths:
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
        return ImageFont.load_default()

    f11 = tf(regular_candidates, 11)
    f12 = tf(regular_candidates, 12)
    f13 = tf(regular_candidates, 13)
    f14 = tf(regular_candidates, 14)
    b11 = tf(bold_candidates, 11)
    b13 = tf(bold_candidates, 13)
    b14 = tf(bold_candidates, 14)
    b16 = tf(bold_candidates, 16)
    b34 = tf(bold_candidates, 34)

    # ── разбор входной структуры ──────────────────────────────────────
    def section_dict(idx):
        if idx >= len(sections):
            return {}
        return {k: v for k, v in sections[idx][1:] if k}

    hdr = section_dict(0)
    kpi_rows = [(k, v) for k, v in sections[1][1:] if k] if len(sections) > 1 else []
    charge_rows = [(k, v) for k, v in sections[2][1:] if k] if len(sections) > 2 else []

    name = hdr.get("Сотрудник", "")
    period = hdr.get("Период", "")
    mr = hdr.get("Основная ставка", ""); ms = hdr.get("Основные смены", "")
    er = hdr.get("Дополнительная ставка", ""); es = hdr.get("Дополнительные смены", "")
    rate_parts = []
    if mr and mr != "—":
        # Было «× 15 см» — сокращение читалось как сантиметры.
        rate_parts.append(f"Осн. {mr} \u00d7 {ms} {_shifts_word(ms)}")
    if er and er != "—":
        rate_parts.append(f"доп. {er} \u00d7 {es} {_shifts_word(es)}")
    rate_line = "   \u00b7   ".join(rate_parts)

    def parse_kpi(s):
        if not s or s.strip() == "—":
            return None
        lines = s.split("\n")
        # Принудительный режим: план не считался вовсе, и строки идут иначе.
        # Прежний разбор брал «7» из «✅ 7%, комиссия: 35 791 ₽» за план, а
        # саму комиссию — за факт, получая выполнение 5113 % и оранжевую
        # полосу во всю ширину. Такой KPI показываем без полосы: сравнивать
        # не с чем.
        if "Принудительно" in lines[0]:
            m = re.search(r'(\d+)%', lines[1] if len(lines) > 1 else "")
            return dict(
                forced="макс." if "макс" in lines[0] else "мин.",
                met="\u2705" in (lines[1] if len(lines) > 1 else ""),
                rate=m.group(0) if m else "",
                plan=0.0, fact=0.0, fulfillment=0.0,
                detail=lines[2] if len(lines) > 2 else "",
                extra=lines[1] if len(lines) > 1 else "",
            )
        met = "\u2705" in lines[0]
        m = re.search(r'(\d+)%', lines[0])
        rate = m.group(0) if m else ""
        plan = fact = 0.0
        if len(lines) > 1:
            nums = re.findall(r'[\d\u202f]+', lines[1])
            if len(nums) >= 2:
                plan = float(re.sub(r'[^\d]', '', nums[0]) or 0)
                fact = float(re.sub(r'[^\d]', '', nums[1]) or 0)
        return dict(
            forced="", met=met, rate=rate, plan=plan, fact=fact,
            fulfillment=fact / plan if plan > 0 else 0.0,
            extra=lines[2] if len(lines) > 2 else "",
            detail=lines[1] if len(lines) > 1 else "",
        )

    kpi_parsed = [(k, parse_kpi(v)) for k, v in kpi_rows]

    charges = []; deductions = []; net_pay = ""; total = ""
    for key, val in charge_rows:
        if key == "К выплате":
            net_pay = val
        elif key == "ИТОГО":
            total = val
            charges.append((key, val))
        elif key in {"Удержание", "Аванс"}:
            # Нулевое удержание — это отсутствие удержания, а не строка отчёта.
            # «− 0 ₽» дважды подряд занимало целую карточку и ничего не
            # сообщало; у кого удержаний не было, тот и не должен их видеть.
            if re.sub(r"[^\d]", "", val or "").strip("0"):
                deductions.append((key, val))
        else:
            charges.append((key, val))

    # ── раскладка ─────────────────────────────────────────────────────
    GAP = 12; CVP = 14; TITLE_H = 30
    HERO_H = 128 if rate_line else 112
    CRH = 28; DIV = 6; DRH = 26
    KNH = 22; KBH = 8; KDH = 16; KEH = 16; KGAP = 12
    KIH = KNH + 4 + KBH + 6 + KDH + 2 + KEH        # обычный KPI, с полосой
    KFH = KNH + 4 + KDH + 2 + KEH                   # принудительный, без полосы
    KNOH = 26                                       # KPI не считался

    def charges_h():
        if not charges:
            return 0
        h = CVP + TITLE_H
        for key, _ in charges:
            h += CRH + (DIV if key == "ИТОГО" else 0)
        return h + CVP - 6

    def ded_h():
        return (CVP + TITLE_H + len(deductions) * DRH + CVP - 6) if deductions else 0

    def kpi_h():
        if not kpi_parsed:
            return 0
        h = CVP + TITLE_H
        for i, (_, p) in enumerate(kpi_parsed):
            h += KNOH if p is None else (KFH if p["forced"] else KIH)
            if i < len(kpi_parsed) - 1:
                h += KGAP
        return h + CVP - 6

    ch, dh, kh = charges_h(), ded_h(), kpi_h()
    H = PAD + HERO_H
    for block in (ch, dh, kh):
        if block:
            H += GAP + block
    H += PAD

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    def rr(x1, y1, x2, y2, r=12, fill=CARD, outline=None, width=1):
        try:
            d.rounded_rectangle([x1, y1, x2, y2], radius=r, fill=fill,
                                outline=outline, width=width)
        except AttributeError:
            d.rectangle([x1, y1, x2, y2], fill=fill, outline=outline)

    def txt(s, x, y, font, color=TEXT, right=False):
        if right:
            x -= d.textlength(s, font=font)
        d.text((x, y), s, font=font, fill=color)

    def pbar(x, y, w, h, pct, color):
        rr(x, y, x + w, y + h, r=h // 2, fill=PBAR_BG)
        fw = max(0, min(int(w * min(pct, 1.0)), w))
        if fw >= 2:
            rr(x, y, x + fw, y + h, r=min(h // 2, fw // 2), fill=color)

    RX = W - IX
    y = PAD

    # ── главное: сумма к выплате ──────────────────────────────────────
    rr(PAD, y, W - PAD, y + HERO_H, outline=BORDER)
    eyebrow = " \u00b7 ".join(x for x in (name, period.capitalize()) if x)
    txt(eyebrow, IX, y + 16, f13, SUBTEXT)
    txt("К выплате", IX, y + 40, f13, SUBTEXT)
    txt(net_pay or "\u2014", IX, y + 56, b34, ACCENT)
    if total:
        d.line([(IX, y + 100), (RX, y + 100)], fill=BORDER, width=1)
        # Одной строкой вся арифметика листа: начислено минус удержано.
        # Разбивку по видам удержаний показывает карточка ниже — здесь
        # важно не «из чего», а «почему на руки меньше, чем начислено».
        held = 0
        for _, v in deductions:
            digits = re.sub(r"[^\d]", "", v or "")
            held += int(digits) if digits else 0
        line = f"Начислено {total}"
        if held:
            line += f"   \u2212   удержано {held:,} \u20bd".replace(",", "\u202f")
        txt(line, IX, y + 108, f12, SUBTEXT)
    y += HERO_H

    # ── начисления ────────────────────────────────────────────────────
    if charges:
        y += GAP
        rr(PAD, y, W - PAD, y + ch, outline=BORDER)
        txt("Начисления", IX, y + CVP, b16, ACCENT)
        if rate_line:
            txt(rate_line, RX, y + CVP + 3, f11, SUBTEXT, right=True)
        cy = y + CVP + TITLE_H
        for key, val in charges:
            is_total = key == "ИТОГО"
            if is_total:
                d.line([(IX, cy), (RX, cy)], fill=BORDER, width=1)
                cy += DIV
            txt(key, IX, cy, b14 if is_total else f14, TEXT if is_total else SUBTEXT)
            txt(val, RX, cy, b16 if is_total else f14, TEXT, right=True)
            cy += CRH
        y += ch

    # ── удержания ─────────────────────────────────────────────────────
    if deductions:
        y += GAP
        rr(PAD, y, W - PAD, y + dh, outline=BORDER)
        txt("Удержано", IX, y + CVP, b16, RED)
        dy = y + CVP + TITLE_H
        for key, val in deductions:
            txt(key, IX, dy, f14, SUBTEXT)
            txt("\u2212\u202f" + val, RX, dy, b14, RED, right=True)
            dy += DRH
        y += dh

    # ── KPI: объяснение, откуда взялись комиссии ──────────────────────
    if kpi_parsed:
        y += GAP
        rr(PAD, y, W - PAD, y + kh, outline=BORDER)
        txt("Выполнение плана", IX, y + CVP, b16, ACCENT)
        ky = y + CVP + TITLE_H
        for i, (kn, p) in enumerate(kpi_parsed):
            if p is None:
                txt(kn, IX, ky, b14)
                txt("план не ставился", RX, ky, f13, SUBTEXT, right=True)
                ky += KNOH
            elif p["forced"]:
                color = GREEN if p["met"] else WARN
                txt(kn, IX, ky, b14)
                txt(f"ставка {p['rate']} \u00b7 принудительно: {p['forced']}",
                    RX, ky + 1, f13, color, right=True)
                ky += KNH + 4
                if p["detail"]:
                    txt(p["detail"], IX, ky, f12, SUBTEXT)
                ky += KDH + 2 + KEH
            else:
                color = GREEN if p["met"] else WARN
                pct = int(round(p["fulfillment"] * 100)) if p["plan"] else 0
                txt(kn, IX, ky, b14)
                # Слева от процента — ставка комиссии: раньше на этом месте
                # стоял только он, и «7%» рядом с полосой прогресса читалось
                # как выполнение плана, хотя это доля от продаж.
                rate_w = d.textlength(f"{pct}%", font=b14)
                txt(f"ставка {p['rate']}", RX - rate_w - 10, ky + 1, f12, SUBTEXT, right=True)
                txt(f"{pct}%", RX, ky, b14, color, right=True)
                ky += KNH + 4
                pbar(IX, ky, RX - IX, KBH, p["fulfillment"], color)
                ky += KBH + 6
                txt(p["detail"], IX, ky, f12, SUBTEXT)
                ky += KDH + 2
                if p["extra"]:
                    txt(p["extra"], IX, ky, f12, RED if "До 80%" in p["extra"] else GREEN)
                ky += KEH
            if i < len(kpi_parsed) - 1:
                ky += KGAP

    img.save(filename)
    log(f"✅ [create_payroll_report_image] Saved: {filename}")
    return filename


# ── Тема оформления расписания ────────────────────────────────────────────
#
# Все цвета и размеры собраны здесь, а не размазаны по рендеру: тёмная тема
# в будущем — это второй такой словарь, без правки логики отрисовки.
#
# Размеры заданы в «единицах макета» при ширине 1080. Рисуется всё в два раза
# крупнее и потом уменьшается (SCALE): у PIL нет сглаживания фигур, и
# скругления без этого выходят ступенчатыми.
SCHEDULE_THEME = {
    "width": 1080,
    "scale": 2,

    "background":        "#F4F5F8",
    "surface":           "#FFFFFF",
    "surface_secondary": "#F6F7FA",
    "border":            "#E9EAF0",
    "text":              "#16171D",
    "text_secondary":    "#8A8D9B",
    "text_muted":        "#B9BCC8",
    "weekend":           "#C9788C",

    "accent":            "#7C4DFF",
    "accent_soft":       "#F1EBFF",
    "accent_border":     "#DCCBFF",
    "accent_text":       "#6D3FE8",

    "radius_card":       24,
    "radius_widget":     16,
    "radius_cell":       16,

    "shadow_color":      (24, 26, 42),
    "shadow_alpha":      26,
    "shadow_blur":       11,
    "shadow_dy":         5,

    "page_pad":          32,
    "card_pad":          26,
    "gap":               18,

    "header_h":          140,
    "weekday_h":         46,
    "cell_h":            134,
    "legend_row_h":      34,
}

# Палитра филиалов. Четыре роли на каждый: заливка карточки, её граница,
# крупный код и подпись. Значения для «Гранд Паласа» (фиолетовый) и
# «Меркурия» (зелёный) заданы по макету, остальные собраны по тому же
# рецепту — мягкая заливка, чуть плотнее граница, насыщенный текст.
SALON_PALETTE = {
    "Гп": {"primary": "#7C4DFF", "bg": "#F1EBFF", "border": "#DCCBFF", "text": "#6D3FE8"},
    "М":  {"primary": "#269B6B", "bg": "#E8F6F0", "border": "#BFE6D3", "text": "#21885E"},
    "Ц":  {"primary": "#3E63D6", "bg": "#E9EEFC", "border": "#C2D0F5", "text": "#3453BC"},
    "А":  {"primary": "#C98A1E", "bg": "#FBF2E1", "border": "#F0DCB2", "text": "#A9731A"},
    "Ох": {"primary": "#2E8CC4", "bg": "#E7F3FA", "border": "#BEDDEF", "text": "#28789F"},
    "Оз": {"primary": "#D96B45", "bg": "#FBEEE9", "border": "#F3D0C2", "text": "#B85A39"},
    "П":  {"primary": "#C4497B", "bg": "#FBEAF2", "border": "#F0C4D8", "text": "#A63C68"},
    "Р":  {"primary": "#8A6B4A", "bg": "#F4EFE9", "border": "#DFD1BF", "text": "#75593D"},
    "Т":  {"primary": "#7E8398", "bg": "#F1F2F6", "border": "#D8DAE3", "text": "#6A6F82"},
}
SALON_FALLBACK = {"primary": "#7C4DFF", "bg": "#F1EBFF",
                  "border": "#DCCBFF", "text": "#6D3FE8"}

# Совместимость: прежний плоский словарь код → цвет всё ещё удобен снаружи.
SALON_COLORS = {code: p["primary"] for code, p in SALON_PALETTE.items()}

WEEKDAY_ORDER = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]

# Segoe UI — системный UI-шрифт Windows, на котором и работает бот: близок к
# SF Pro по рисунку, полная кириллица, есть все нужные начертания. Inter в
# системе нет — пакет @fontsource во фронтенде отдаёт только woff2, а их PIL
# не читает. Дальше по списку — то, что найдётся на Linux.
_UI_FONTS = {
    "regular":  ["segoeui.ttf", "C:/Windows/Fonts/segoeui.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                 "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"],
    "semibold": ["seguisb.ttf", "C:/Windows/Fonts/seguisb.ttf",
                 "segoeuib.ttf", "C:/Windows/Fonts/segoeuib.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"],
    "bold":     ["segoeuib.ttf", "C:/Windows/Fonts/segoeuib.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"],
}


def _ui_font(weight: str, size: int):
    for path in _UI_FONTS.get(weight, _UI_FONTS["regular"]):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _salon_info() -> dict:
    """Код филиала → {name, weekday, weekend}. Пустой словарь, если справочника нет.

    Читается лениво и через try: картинка не должна падать из-за
    отсутствующего salons.json — подписи и часы просто не появятся.
    """
    try:
        from ..data.salon_repository import SalonRepository
        out = {}
        for s in SalonRepository().list_salons():
            if not s.code:
                continue
            out[s.code] = {
                "name": s.name or "",
                "weekday": (getattr(s, "work_hours_weekday", "") or "").strip(),
                "weekend": (getattr(s, "work_hours_weekend", "") or "").strip(),
            }
        return out
    except Exception:
        return {}


def _ru_quotes(s: str) -> str:
    """Прямые кавычки → «ёлочки». Правится подача, а не сам справочник."""
    out, opening = [], True
    for ch in s or "":
        if ch == '"':
            out.append("«" if opening else "»")
            opening = not opening
        else:
            out.append(ch)
    return "".join(out)


def _hours_label(info: dict, weekend: bool) -> str:
    """«10:00-22:00» из справочника → «10:00 – 22:00». Пусто, если часов нет."""
    raw = (info.get("weekend") if weekend else info.get("weekday")) or ""
    raw = raw.strip() or (info.get("weekday") or "").strip()
    if not raw or "-" not in raw:
        return raw
    left, _, right = raw.partition("-")
    return f"{left.strip()} \u2013 {right.strip()}"


def create_schedule_image(data, employee_name, sheet_name, weekdays):
    """Расписание сотрудника на месяц — экраном мобильного приложения.

    Данные и их разбор те же, что и раньше: строка сотрудника из листа Excel,
    колонки-дни, коды филиалов в ячейках. Переработан только визуальный слой.

    Сетка 7 колонок строится по дням недели из листа, а не по календарю:
    Excel остаётся единственным источником правды о том, какой день каким был.
    Рабочий день — карточка цветом филиала с кодом и часами работы (часы
    берутся из справочника салонов), выходной — спокойная пустая клетка.

    Композиция: шапка с именем и счётчиком смен, календарь, легенда. Всё
    оформление — в SCHEDULE_THEME и SALON_PALETTE.
    """
    compare_name = employee_name.lower()
    employee_rows = data[data["ИМЯ"].astype(str).str.lower() == compare_name]
    if employee_rows.empty:
        log(f"❌ [create_schedule_image] Нет данных для сотрудника {employee_name} (поиск: {compare_name})")
        return None
    employee_row = employee_rows.iloc[0]

    valid_day_cols = []
    for col in data.columns[2:]:
        try:
            day_val = int(col)
            if 1 <= day_val <= 31:
                valid_day_cols.append(col)
            else:
                break
        except (ValueError, TypeError):
            break
    if not valid_day_cols:
        log(f"❌ [create_schedule_image] Нет подходящих данных о днях месяца в столбцах: {data.columns[2:].tolist()}")
        return None

    day_numbers = [str(int(col)) for col in valid_day_cols]
    num_days = len(day_numbers)
    # Дни недели приходят срезом weekdays_row[2:33] и в принципе могут
    # оказаться короче месяца — добиваем пустыми, чтобы обращение по индексу
    # не роняло отправку расписания целиком.
    day_weekdays = [str(wd).strip().lower() for wd in weekdays[:num_days]]
    day_weekdays += [""] * (num_days - len(day_weekdays))
    schedule_values = [
        "" if pd.isna(employee_row[col]) else str(employee_row[col]).strip()
        for col in valid_day_cols
    ]
    log(f"DEBUG [create_schedule_image] Расписание: {schedule_values}, Дни недели: {day_weekdays}")

    T = SCHEDULE_THEME
    S = T["scale"]
    W = T["width"]

    first_wd = day_weekdays[0] if day_weekdays else "пн"
    offset = WEEKDAY_ORDER.index(first_wd) if first_wd in WEEKDAY_ORDER else 0
    weeks = -(-(offset + num_days) // 7)

    shifts = sum(1 for v in schedule_values if v)
    used_codes = []
    for v in schedule_values:
        if v and v not in used_codes:
            used_codes.append(v)
    info = _salon_info()

    # ── высоты блоков ─────────────────────────────────────────────────
    PAD, CPAD, GAP = T["page_pad"], T["card_pad"], T["gap"]
    head_h = T["header_h"]
    cal_h = CPAD + T["weekday_h"] + weeks * T["cell_h"] + CPAD - 6
    legend_h = (CPAD + len(used_codes) * T["legend_row_h"] + CPAD - 8) if used_codes else 0
    H = PAD + head_h + GAP + cal_h + ((GAP + legend_h) if legend_h else 0) + PAD

    # ── холст ─────────────────────────────────────────────────────────
    img = Image.new("RGBA", (W * S, H * S), T["background"])
    d = ImageDraw.Draw(img)

    def px(v):
        return int(round(v * S))

    def font(weight, size):
        return _ui_font(weight, px(size))

    def rrect(x1, y1, x2, y2, radius, fill=None, outline=None, width=1.0):
        d.rounded_rectangle([px(x1), px(y1), px(x2), px(y2)], radius=px(radius),
                            fill=fill, outline=outline,
                            width=max(1, px(width)) if outline else 0)

    def shadow(boxes):
        """Мягкая тень под карточками: отдельный слой с размытием.

        Рисуется до самих карточек, поэтому все тени лежат под всеми
        поверхностями и не проступают на соседних.
        """
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        col = tuple(T["shadow_color"]) + (T["shadow_alpha"],)
        for (x1, y1, x2, y2, r) in boxes:
            ld.rounded_rectangle(
                [px(x1 + 3), px(y1 + T["shadow_dy"]), px(x2 - 3), px(y2 + T["shadow_dy"])],
                radius=px(r), fill=col)
        layer = layer.filter(ImageFilter.GaussianBlur(px(T["shadow_blur"])))
        img.alpha_composite(layer)

    def text(s, x, y, fnt, fill, anchor="la"):
        d.text((px(x), px(y)), s, font=fnt, fill=fill, anchor=anchor)

    def text_w(s, fnt):
        return d.textlength(s, font=fnt) / S

    def tracked(s, x, y, fnt, fill, tracking, center_in=None):
        """Текст с разрядкой — у PIL её нет, рисуем посимвольно.

        Нужна только для мелких капсовых подписей: без неё они выглядят
        сжатыми, а именно они задают спокойный «интерфейсный» тон.
        """
        widths = [d.textlength(ch, font=fnt) / S for ch in s]
        total = sum(widths) + tracking * max(0, len(s) - 1)
        if center_in is not None:
            x = center_in - total / 2
        for ch, w in zip(s, widths):
            d.text((px(x), px(y)), ch, font=fnt, fill=fill)
            x += w + tracking
        return total

    def fit_font(s, weight, size, max_w, min_size):
        """Подобрать кегль так, чтобы строка влезла в ширину."""
        while size > min_size:
            f = font(weight, size)
            if text_w(s, f) <= max_w:
                return f
            size -= 1
        return font(weight, min_size)

    def ellipsize(s, fnt, max_w):
        if text_w(s, fnt) <= max_w:
            return s
        while s and text_w(s + "\u2026", fnt) > max_w:
            s = s[:-1]
        return (s.rstrip() + "\u2026") if s else ""

    # ── тени всех карточек одним слоем ────────────────────────────────
    y_head = PAD
    y_cal = y_head + head_h + GAP
    y_leg = y_cal + cal_h + GAP
    boxes = [(PAD, y_head, W - PAD, y_head + head_h, T["radius_card"]),
             (PAD, y_cal, W - PAD, y_cal + cal_h, T["radius_card"])]
    if legend_h:
        boxes.append((PAD, y_leg, W - PAD, y_leg + legend_h, T["radius_card"]))
    shadow(boxes)

    # ── шапка ─────────────────────────────────────────────────────────
    rrect(PAD, y_head, W - PAD, y_head + head_h, T["radius_card"], fill=T["surface"])

    WIDGET_W, WIDGET_H = 194, 104
    wx2 = W - PAD - CPAD
    wx1 = wx2 - WIDGET_W
    wy1 = y_head + (head_h - WIDGET_H) / 2

    # Имя и табельный номер: номер тем же кеглем, но акцентным цветом —
    # человек ищет глазами имя, номер нужен для сверки и не должен спорить.
    name_x = PAD + CPAD
    name_limit = wx1 - name_x - 28
    parts = employee_name.strip().rsplit(" ", 1)
    if len(parts) == 2 and parts[1].isdigit():
        base_name, tab_no = parts[0], parts[1]
    else:
        base_name, tab_no = employee_name.strip(), ""
    f_name = fit_font(f"{base_name} {tab_no}".strip(), "bold", 42, name_limit, 26)
    text(base_name, name_x, y_head + 36, f_name, T["text"])
    if tab_no:
        text(" " + tab_no, name_x + text_w(base_name, f_name), y_head + 36,
             f_name, T["accent"])

    f_sub = font("semibold", 16)
    tracked(f"{sheet_name.upper()} \u00b7 ГРАФИК РАБОТЫ", name_x, y_head + 92,
            f_sub, T["text_secondary"], 1.4)

    rrect(wx1, wy1, wx2, wy1 + WIDGET_H, T["radius_widget"], fill=T["accent_soft"])
    cx = (wx1 + wx2) / 2
    text(str(shifts), cx, wy1 + 16, font("bold", 46), T["accent"], anchor="ma")
    tracked("СМЕН В МЕСЯЦЕ", 0, wy1 + 73, font("semibold", 12),
            T["accent_text"], 1.0, center_in=cx)

    # ── календарь ─────────────────────────────────────────────────────
    rrect(PAD, y_cal, W - PAD, y_cal + cal_h, T["radius_card"], fill=T["surface"])

    grid_x = PAD + CPAD
    grid_w = W - 2 * PAD - 2 * CPAD
    CW = grid_w / 7
    CH = T["cell_h"]

    f_wd = font("semibold", 16)
    for i, wd in enumerate(WEEKDAY_ORDER):
        tracked(wd.upper(), 0, y_cal + CPAD + 12, f_wd,
                T["weekend"] if i >= 5 else T["text_secondary"], 1.6,
                center_in=grid_x + i * CW + CW / 2)

    gy = y_cal + CPAD + T["weekday_h"]
    f_day = font("semibold", 19)
    f_day_off = font("regular", 19)

    for idx in range(num_days):
        pos = offset + idx
        col_i, row_i = pos % 7, pos // 7
        x0 = grid_x + col_i * CW
        y0 = gy + row_i * CH
        # Между карточками — воздух, а не линии сетки: таблица получается
        # именно из линий, а нужен список карточек.
        cx1, cy1 = x0 + 4, y0 + 4
        cx2, cy2 = x0 + CW - 4, y0 + CH - 10
        code = schedule_values[idx]
        weekend = day_weekdays[idx] in ("сб", "вс")

        if code:
            pal = SALON_PALETTE.get(code, SALON_FALLBACK)
            rrect(cx1, cy1, cx2, cy2, T["radius_cell"],
                  fill=pal["bg"], outline=pal["border"], width=1.5)
            text(day_numbers[idx], cx1 + 13, cy1 + 11, f_day, pal["text"])
            mid = (cx1 + cx2) / 2
            f_code = fit_font(code, "bold", 32, (cx2 - cx1) - 22, 17)
            hours = _hours_label(info.get(code, {}), weekend)
            # Без часов (в справочнике их может не быть) код встаёт по центру
            # карточки: иначе под ним остаётся дыра, и такой день выглядит
            # обрезанным рядом с соседними.
            text(code, mid, cy1 + (40 if hours else 52), f_code,
                 pal["primary"], anchor="ma")
            if hours:
                f_h = fit_font(hours, "regular", 17, (cx2 - cx1) - 14, 12)
                text(hours, mid, cy2 - 30, f_h, pal["text"], anchor="ma")
        else:
            # Выходной остаётся фоном: заливка едва отличается от карточки,
            # граница почти неразличима — рабочие дни должны выступать сами,
            # без того чтобы соревноваться с пустыми клетками.
            rrect(cx1, cy1, cx2, cy2, T["radius_cell"],
                  fill=T["surface_secondary"])
            text(day_numbers[idx], cx1 + 13, cy1 + 11, f_day_off,
                 T["weekend"] if weekend else T["text_muted"])

    # ── легенда ───────────────────────────────────────────────────────
    if used_codes:
        rrect(PAD, y_leg, W - PAD, y_leg + legend_h, T["radius_card"], fill=T["surface"])
        f_code = font("bold", 17)
        f_name_l = font("regular", 17)
        ly = y_leg + CPAD
        for code in used_codes:
            pal = SALON_PALETTE.get(code, SALON_FALLBACK)
            dot_r = 5
            dcx, dcy = grid_x + dot_r, ly + 13
            d.ellipse([px(dcx - dot_r), px(dcy - dot_r), px(dcx + dot_r), px(dcy + dot_r)],
                      fill=pal["primary"])
            text(code, grid_x + 24, ly + 3, f_code, T["text"])
            title = _ru_quotes((info.get(code, {}) or {}).get("name", ""))
            if title:
                tx = grid_x + 24 + max(text_w(code, f_code), 34) + 16
                text(ellipsize(title, f_name_l, W - PAD - CPAD - tx),
                     tx, ly + 3, f_name_l, T["text_secondary"])
            ly += T["legend_row_h"]

    filename = f"schedule_{employee_name}.png"
    img.convert("RGB").resize((W, H), Image.LANCZOS).save(filename)
    log(f"✅ [create_schedule_image] Файл создан: {filename}")
    return filename
