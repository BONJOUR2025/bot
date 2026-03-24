from PIL import Image, ImageDraw, ImageFont
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


def create_payroll_report_image(sections: list, filename: str = "salary_report.png"):
    """Modern dark-themed payroll report image (for SQL/Firebird source).

    Expects sections in the format returned by generate_employee_report_from_payroll().
    """
    BG = "#F0F2F8"; CARD = "#FFFFFF"; ACCENT = "#4A6CF7"
    GREEN = "#2E7D32"; ORANGE = "#E65100"; RED = "#C62828"
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

    f12 = tf(regular_candidates, 12)
    f13 = tf(regular_candidates, 13)
    f14 = tf(regular_candidates, 14)
    b14 = tf(bold_candidates, 14)
    b16 = tf(bold_candidates, 16)
    b20 = tf(bold_candidates, 20)

    # ── extract data ──────────────────────────────────────
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
        rate_parts.append(f"Осн: {mr} \u00d7 {ms} см")
    if er and er != "—":
        rate_parts.append(f"Доп: {er} \u00d7 {es} см")
    rate_line = "   ".join(rate_parts)

    def parse_kpi(s):
        if not s or s.strip() == "—":
            return None
        lines = s.split("\n")
        met = "\u2705" in lines[0]
        m = re.search(r'(\d+)%', lines[0])
        pct = m.group(0) if m else ""
        plan = fact = 0.0
        if len(lines) > 1:
            nums = re.findall(r'[\d\u202f]+', lines[1])
            if len(nums) >= 2:
                plan = float(re.sub(r'[^\d]', '', nums[0]) or 0)
                fact = float(re.sub(r'[^\d]', '', nums[1]) or 0)
        return dict(
            met=met, pct=pct, plan=plan, fact=fact,
            fulfillment=fact / plan if plan > 0 else 0.0,
            extra=lines[2] if len(lines) > 2 else "",
            detail=lines[1] if len(lines) > 1 else "",
        )

    kpi_parsed = [(k, parse_kpi(v)) for k, v in kpi_rows]

    charges = []; deductions = []; net_pay = ""
    for key, val in charge_rows:
        if key == "К выплате":
            net_pay = val
        elif key in {"Удержание", "Аванс"}:
            deductions.append((key, val))
        else:
            charges.append((key, val))

    # ── layout ────────────────────────────────────────────
    GAP = 10; CVP = 14; TITLE_H = 30; HEADER_H = 80
    KNH = 22; KBH = 10; KDH = 16; KEH = 16; KGAP = 10
    KIH = KNH + 4 + KBH + 4 + KDH + 4 + KEH
    KNOH = 26; CRH = 28; DIV = 6; DRH = 26; NET_H = 44

    def kpi_card_h():
        if not kpi_parsed:
            return 0
        h = CVP + TITLE_H
        for i, (_, p) in enumerate(kpi_parsed):
            h += KIH if p else KNOH
            if i < len(kpi_parsed) - 1:
                h += KGAP
        return h + CVP

    def charge_card_h():
        h = CVP + TITLE_H
        for key, _ in charges:
            h += CRH
            if key == "ИТОГО":
                h += DIV
        return h + CVP

    def ded_card_h():
        return CVP + len(deductions) * DRH + CVP if deductions else 0

    kh = kpi_card_h(); ch = charge_card_h(); dh = ded_card_h()
    blocks = [
        (HEADER_H, True),
        (kh, bool(kpi_parsed)),
        (ch, bool(charges)),
        (dh, bool(deductions)),
        (NET_H, bool(net_pay)),
    ]
    H = PAD
    for bh, vis in blocks:
        if vis:
            H += bh + GAP
    H += PAD - GAP  # replace last gap with bottom padding

    # ── drawing helpers ───────────────────────────────────
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    def rr(x1, y1, x2, y2, r=12, fill=CARD, outline=None):
        try:
            d.rounded_rectangle([x1, y1, x2, y2], radius=r, fill=fill, outline=outline)
        except AttributeError:
            d.rectangle([x1, y1, x2, y2], fill=fill, outline=outline)

    def txt(s, x, y, font, color=TEXT, right=False):
        if right:
            w = d.textlength(s, font=font)
            d.text((x - w, y), s, font=font, fill=color)
        else:
            d.text((x, y), s, font=font, fill=color)

    def pbar(x, y, w, h, pct, color):
        rr(x, y, x + w, y + h, r=h // 2, fill=PBAR_BG)
        fw = max(0, min(int(w * min(pct, 1.0)), w))
        if fw >= 2:
            rr(x, y, x + fw, y + h, r=min(h // 2, fw // 2), fill=color)

    RX = W - IX
    y = PAD

    # header card
    rr(PAD, y, W - PAD, y + HEADER_H, outline=BORDER)
    txt(name, IX, y + 14, b20)
    txt(period, RX, y + 16, f14, SUBTEXT, right=True)
    if rate_line:
        txt(rate_line, IX, y + 48, f13, SUBTEXT)
    y += HEADER_H + GAP

    # KPI card
    if kpi_parsed:
        rr(PAD, y, W - PAD, y + kh, outline=BORDER)
        txt("KPI", IX, y + CVP, b16, ACCENT)
        ky = y + CVP + TITLE_H
        for i, (kn, p) in enumerate(kpi_parsed):
            if p is None:
                txt(kn, IX, ky, b14)
                txt("—", RX, ky, f14, SUBTEXT, right=True)
                ky += KNOH
            else:
                color = GREEN if p["met"] else ORANGE
                txt(kn, IX, ky, b14)
                txt(p["pct"], RX, ky, b14, color, right=True)
                ky += KNH + 4
                pbar(IX, ky, W - IX * 2, KBH, p["fulfillment"], color)
                ky += KBH + 4
                txt(p["detail"], IX, ky, f12, SUBTEXT)
                ky += KDH + 4
                ec = RED if "До 80%" in p["extra"] else GREEN
                if p["extra"]:
                    txt(p["extra"], IX, ky, f12, ec)
                ky += KEH
            if i < len(kpi_parsed) - 1:
                ky += KGAP
        y += kh + GAP

    # charges card
    if charges:
        rr(PAD, y, W - PAD, y + ch, outline=BORDER)
        txt("Начисления", IX, y + CVP, b16, ACCENT)
        cy = y + CVP + TITLE_H
        for key, val in charges:
            is_total = key == "ИТОГО"
            if is_total:
                d.line([(IX, cy), (W - IX, cy)], fill=BORDER, width=1)
                cy += DIV
            txt(key, IX, cy, b14 if is_total else f14, TEXT if is_total else SUBTEXT)
            txt(val, RX, cy, b16 if is_total else f14, TEXT, right=True)
            cy += CRH
        y += ch + GAP

    # deductions card
    if deductions:
        rr(PAD, y, W - PAD, y + dh, outline=BORDER)
        dy = y + CVP
        for key, val in deductions:
            txt(key, IX, dy, f14, SUBTEXT)
            txt("\u2212\u202f" + val, RX, dy, b14, RED, right=True)
            dy += DRH
        y += dh + GAP

    # net pay banner
    if net_pay:
        rr(PAD, y, W - PAD, y + NET_H, r=10, fill=ACCENT)
        ny = y + (NET_H - 14) // 2
        txt("К выплате", IX, ny, b16, "#FFFFFF")
        txt(net_pay, RX, ny, b16, "#FFFFFF", right=True)

    img.save(filename)
    log(f"✅ [create_payroll_report_image] Saved: {filename}")
    return filename


def create_schedule_image(data, employee_name, sheet_name, weekdays):
    """Создаёт изображение расписания для выбранного сотрудника и месяца."""
    compare_name = employee_name.lower()
    employee_rows = data[data["ИМЯ"].astype(str).str.lower() == compare_name]
    if employee_rows.empty:
        log(
            f"❌ [create_schedule_image] Нет данных для сотрудника {employee_name} (поиск: {compare_name})"
        )
        return None
    employee_row = employee_rows.iloc[0]
    log(
        f"DEBUG [create_schedule_image] Данные сотрудника: {employee_row.to_dict()}"
    )

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
        log(
            f"❌ [create_schedule_image] Нет подходящих данных о днях месяца в столбцах: {data.columns[2:].tolist()}"
        )
        return None
    log(
        f"DEBUG [create_schedule_image] Найдены столбцы дней: {valid_day_cols}"
    )

    day_numbers = [str(int(col)) for col in valid_day_cols]
    day_weekdays = [
        str(wd).strip() for wd in weekdays[: len(valid_day_cols)]
    ]  # Используем переданные дни недели
    num_days = len(day_numbers)
    schedule_values = [
        "" if pd.isna(employee_row[col]) else str(employee_row[col])
        for col in valid_day_cols
    ]
    log(
        f"DEBUG [create_schedule_image] Расписание: {schedule_values}, Дни недели: {day_weekdays}"
    )

    cell_width = 50
    cell_height = 40
    left_width = 150
    month_header_height = 30
    daynum_header_height = 40
    weekday_header_height = 40
    data_row_height = 40

    img_width = left_width + cell_width * num_days
    img_height = (
        month_header_height
        + daynum_header_height
        + weekday_header_height
        + data_row_height
    )

    img = Image.new("RGB", (img_width, img_height), "white")
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except IOError:
        font = ImageFont.load_default()

    draw.rectangle(
        [0, 0, img_width, month_header_height], fill="#E0E0E0", outline="black"
    )
    month_text = sheet_name.upper()
    bbox = draw.textbbox((0, 0), month_text, font=font)
    w_text, h_text = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((img_width - w_text) / 2, (month_header_height - h_text) / 2),
        month_text,
        font=font,
        fill="black",
    )

    y_daynum_top = month_header_height
    y_daynum_bottom = y_daynum_top + daynum_header_height
    draw.rectangle(
        [0, y_daynum_top, left_width, y_daynum_bottom],
        fill="#D3D3D3",
        outline="black",
    )
    for i, day in enumerate(day_numbers):
        x0 = left_width + i * cell_width
        x1 = x0 + cell_width
        fill_color = (
            "#FF0000" if day_weekdays[i].lower() in ["сб", "вс"] else "#D3D3D3"
        )
        text_color = (
            "white" if day_weekdays[i].lower() in ["сб", "вс"] else "black"
        )
        draw.rectangle(
            [x0, y_daynum_top, x1, y_daynum_bottom],
            fill=fill_color,
            outline="black",
        )
        bbox = draw.textbbox((0, 0), day, font=font)
        w_day, h_day = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            (
                x0 + (cell_width - w_day) / 2,
                y_daynum_top + (daynum_header_height - h_day) / 2,
            ),
            day,
            font=font,
            fill=text_color,
        )

    y_weekday_top = y_daynum_bottom
    y_weekday_bottom = y_weekday_top + weekday_header_height
    draw.rectangle(
        [0, y_weekday_top, left_width, y_weekday_bottom],
        fill="#A9A9A9",
        outline="black",
    )
    for i, wd in enumerate(day_weekdays):
        x0 = left_width + i * cell_width
        x1 = x0 + cell_width
        fill_color = "#FF0000" if wd.lower() in ["сб", "вс"] else "#A9A9A9"
        text_color = "white" if wd.lower() in ["сб", "вс"] else "black"
        draw.rectangle(
            [x0, y_weekday_top, x1, y_weekday_bottom],
            fill=fill_color,
            outline="black",
        )
        bbox = draw.textbbox((0, 0), wd, font=font)
        w_wd, h_wd = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            (
                x0 + (cell_width - w_wd) / 2,
                y_weekday_top + (weekday_header_height - h_wd) / 2,
            ),
            wd,
            font=font,
            fill=text_color,
        )

    y_data_top = y_weekday_bottom
    y_data_bottom = y_data_top + data_row_height
    draw.rectangle(
        [0, y_data_top, left_width, y_data_bottom],
        fill="#D3D3D3",
        outline="black",
    )
    bbox = draw.textbbox((0, 0), employee_name, font=font)
    w_emp, h_emp = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((left_width - w_emp) / 2, y_data_top + (data_row_height - h_emp) / 2),
        employee_name,
        font=font,
        fill="black",
    )
    for i, val_str in enumerate(schedule_values):
        x0 = left_width + i * cell_width
        y0 = y_data_top
        cell_bg = (
            "#FF0000" if day_weekdays[i].lower() in ["сб", "вс"] else "#FFFFFF"
        )
        text_color = (
            "white" if day_weekdays[i].lower() in ["сб", "вс"] else "black"
        )
        draw.rectangle(
            [x0, y0, x0 + cell_width, y0 + data_row_height],
            fill=cell_bg,
            outline="black",
        )
        bbox = draw.textbbox((0, 0), val_str, font=font)
        w_val, h_val = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            (
                x0 + (cell_width - w_val) / 2,
                y0 + (data_row_height - h_val) / 2,
            ),
            val_str,
            font=font,
            fill=text_color,
        )

    filename = f"schedule_{employee_name}.png"
    img.save(filename)
    log(f"✅ [create_schedule_image] Файл создан: {filename}")
    return filename
