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


# ── Общий слой рисования для картинок бота ────────────────────────────────
#
# Расписание и расчётный лист — два экрана одного приложения, поэтому
# примитивы у них общие: холст с удвоенным разрешением, скруглённые карточки,
# мягкие тени, разрядка у капсовых подписей, подбор кегля под ширину.
# Раньше всё это жило замыканиями внутри одного рендера, и второй пришлось бы
# либо копировать, либо расходиться с первым.
#
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


def _ru_quotes(s: str) -> str:
    """Прямые кавычки → «ёлочки». Правится подача, а не сам справочник."""
    out, opening = [], True
    for ch in s or "":
        if ch == '"':
            out.append("\u00ab" if opening else "\u00bb")
            opening = not opening
        else:
            out.append(ch)
    return "".join(out)


class _Canvas:
    """Холст в «единицах макета» с отрисовкой в удвоенном разрешении.

    У PIL нет сглаживания фигур: скруглённые углы и тонкие линии в один
    проход выходят ступенчатыми. Поэтому всё рисуется крупнее, а на выходе
    уменьшается — заодно сглаживается и текст.

    Все координаты и кегли задаются в единицах макета, масштаб внутри.
    """

    def __init__(self, width: int, height: int, background: str, scale: int = 2):
        self.S = scale
        self.w, self.h = int(width), int(height)
        self.img = Image.new("RGBA", (self.w * scale, self.h * scale), background)
        self.d = ImageDraw.Draw(self.img)

    def px(self, v) -> int:
        return int(round(v * self.S))

    def font(self, weight: str, size: int):
        return _ui_font(weight, self.px(size))

    # ── фигуры ────────────────────────────────────────────────────────
    def rrect(self, x1, y1, x2, y2, radius, fill=None, outline=None, width=1.0):
        self.d.rounded_rectangle(
            [self.px(x1), self.px(y1), self.px(x2), self.px(y2)],
            radius=self.px(radius), fill=fill, outline=outline,
            width=max(1, self.px(width)) if outline else 0)

    def dot(self, cx, cy, r, fill):
        self.d.ellipse([self.px(cx - r), self.px(cy - r),
                        self.px(cx + r), self.px(cy + r)], fill=fill)

    def line(self, x1, y, x2, fill, width=1):
        self.d.line([(self.px(x1), self.px(y)), (self.px(x2), self.px(y))],
                    fill=fill, width=max(1, self.px(width)))

    def bar(self, x, y, w, h, pct, track, fill):
        """Полоса выполнения со скруглением в половину высоты."""
        self.rrect(x, y, x + w, y + h, h / 2, fill=track)
        fw = max(0.0, min(pct, 1.0)) * w
        if self.px(fw) >= 2:
            self.rrect(x, y, x + max(fw, h), y + h, h / 2, fill=fill)

    def shadow(self, boxes, color, alpha: int, blur: float, dy: float):
        """Мягкая тень под карточками — отдельный размытый слой.

        Рисуется до самих карточек, поэтому тени лежат под всеми
        поверхностями и не проступают на соседних.
        """
        layer = Image.new("RGBA", self.img.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        col = tuple(color) + (alpha,)
        for (x1, y1, x2, y2, r) in boxes:
            ld.rounded_rectangle(
                [self.px(x1 + 3), self.px(y1 + dy), self.px(x2 - 3), self.px(y2 + dy)],
                radius=self.px(r), fill=col)
        self.img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(self.px(blur))))

    # ── текст ─────────────────────────────────────────────────────────
    def text(self, s, x, y, font, fill, anchor="la"):
        self.d.text((self.px(x), self.px(y)), s, font=font, fill=fill, anchor=anchor)

    def text_w(self, s, font) -> float:
        return self.d.textlength(s, font=font) / self.S

    def tracked(self, s, x, y, font, fill, tracking, center_in=None) -> float:
        """Текст с разрядкой — у PIL её нет, рисуем посимвольно.

        Нужна мелким капсовым подписям: без неё они выглядят сжатыми, а
        именно они задают спокойный «интерфейсный» тон.
        """
        widths = [self.d.textlength(ch, font=font) / self.S for ch in s]
        total = sum(widths) + tracking * max(0, len(s) - 1)
        if center_in is not None:
            x = center_in - total / 2
        for ch, w in zip(s, widths):
            self.d.text((self.px(x), self.px(y)), ch, font=font, fill=fill)
            x += w + tracking
        return total

    def fit_font(self, s, weight, size, max_w, min_size):
        """Подобрать кегль так, чтобы строка влезла в ширину."""
        while size > min_size:
            f = self.font(weight, size)
            if self.text_w(s, f) <= max_w:
                return f
            size -= 1
        return self.font(weight, min_size)

    def ellipsize(self, s, font, max_w) -> str:
        if self.text_w(s, font) <= max_w:
            return s
        while s and self.text_w(s + "\u2026", font) > max_w:
            s = s[:-1]
        return (s.rstrip() + "\u2026") if s else ""

    # ── вывод ─────────────────────────────────────────────────────────
    def save(self, filename: str) -> str:
        self.img.convert("RGB").resize((self.w, self.h), Image.LANCZOS).save(filename)
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


# ── Расписание сотрудника ─────────────────────────────────────────────────
#
# Все цвета и размеры собраны здесь, а не размазаны по рендеру: тёмная тема
# в будущем — это второй такой словарь, без правки логики отрисовки.
# Размеры заданы в «единицах макета» при ширине 1080 (см. _Canvas).
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


def _hours_label(info: dict, weekend: bool) -> str:
    """«10:00-22:00» из справочника → «10:00 – 22:00». Пусто, если часов нет."""
    raw = (info.get("weekend") if weekend else info.get("weekday")) or ""
    raw = raw.strip() or (info.get("weekday") or "").strip()
    if not raw or "-" not in raw:
        return raw
    left, _, right = raw.partition("-")
    return f"{left.strip()} – {right.strip()}"


def create_schedule_image(data, employee_name, sheet_name, weekdays):
    """Расписание сотрудника на месяц — экраном мобильного приложения.

    Данные и их разбор те же, что и раньше: строка сотрудника из листа Excel,
    колонки-дни, коды филиалов в ячейках. Переработан только визуальный слой.

    Сетка 7 колонок строится по дням недели из листа, а не по календарю:
    Excel остаётся единственным источником правды о том, какой день каким был.
    Рабочий день — карточка цветом филиала с кодом и часами работы (часы
    берутся из справочника салонов), выходной — спокойная пустая клетка.
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

    PAD, CPAD, GAP = T["page_pad"], T["card_pad"], T["gap"]
    head_h = T["header_h"]
    cal_h = CPAD + T["weekday_h"] + weeks * T["cell_h"] + CPAD - 6
    legend_h = (CPAD + len(used_codes) * T["legend_row_h"] + CPAD - 8) if used_codes else 0
    H = PAD + head_h + GAP + cal_h + ((GAP + legend_h) if legend_h else 0) + PAD

    c = _Canvas(W, H, T["background"], T["scale"])

    y_head = PAD
    y_cal = y_head + head_h + GAP
    y_leg = y_cal + cal_h + GAP
    boxes = [(PAD, y_head, W - PAD, y_head + head_h, T["radius_card"]),
             (PAD, y_cal, W - PAD, y_cal + cal_h, T["radius_card"])]
    if legend_h:
        boxes.append((PAD, y_leg, W - PAD, y_leg + legend_h, T["radius_card"]))
    c.shadow(boxes, T["shadow_color"], T["shadow_alpha"], T["shadow_blur"], T["shadow_dy"])

    # ── шапка ─────────────────────────────────────────────────────────
    c.rrect(PAD, y_head, W - PAD, y_head + head_h, T["radius_card"], fill=T["surface"])

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
    f_name = c.fit_font(f"{base_name} {tab_no}".strip(), "bold", 42, name_limit, 26)
    c.text(base_name, name_x, y_head + 36, f_name, T["text"])
    if tab_no:
        c.text(" " + tab_no, name_x + c.text_w(base_name, f_name), y_head + 36,
               f_name, T["accent"])

    c.tracked(f"{sheet_name.upper()} · ГРАФИК РАБОТЫ", name_x, y_head + 94,
              c.font("semibold", 16), T["text_secondary"], 1.4)

    c.rrect(wx1, wy1, wx2, wy1 + WIDGET_H, T["radius_widget"], fill=T["accent_soft"])
    cx = (wx1 + wx2) / 2
    c.text(str(shifts), cx, wy1 + 16, c.font("bold", 46), T["accent"], anchor="ma")
    c.tracked("СМЕН В МЕСЯЦЕ", 0, wy1 + 73, c.font("semibold", 12),
              T["accent_text"], 1.0, center_in=cx)

    # ── календарь ─────────────────────────────────────────────────────
    c.rrect(PAD, y_cal, W - PAD, y_cal + cal_h, T["radius_card"], fill=T["surface"])

    grid_x = PAD + CPAD
    grid_w = W - 2 * PAD - 2 * CPAD
    CW = grid_w / 7
    CH = T["cell_h"]

    f_wd = c.font("semibold", 16)
    for i, wd in enumerate(WEEKDAY_ORDER):
        c.tracked(wd.upper(), 0, y_cal + CPAD + 12, f_wd,
                  T["weekend"] if i >= 5 else T["text_secondary"], 1.6,
                  center_in=grid_x + i * CW + CW / 2)

    gy = y_cal + CPAD + T["weekday_h"]
    f_day = c.font("semibold", 19)
    f_day_off = c.font("regular", 19)

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
            c.rrect(cx1, cy1, cx2, cy2, T["radius_cell"],
                    fill=pal["bg"], outline=pal["border"], width=1.5)
            c.text(day_numbers[idx], cx1 + 13, cy1 + 11, f_day, pal["text"])
            mid = (cx1 + cx2) / 2
            f_code = c.fit_font(code, "bold", 32, (cx2 - cx1) - 22, 17)
            hours = _hours_label(info.get(code, {}), weekend)
            # Без часов (в справочнике их может не быть) код встаёт по центру
            # карточки: иначе под ним остаётся дыра, и такой день выглядит
            # обрезанным рядом с соседними.
            c.text(code, mid, cy1 + (40 if hours else 52), f_code,
                   pal["primary"], anchor="ma")
            if hours:
                f_h = c.fit_font(hours, "regular", 17, (cx2 - cx1) - 14, 12)
                c.text(hours, mid, cy2 - 30, f_h, pal["text"], anchor="ma")
        else:
            # Выходной остаётся фоном: заливка едва отличается от карточки,
            # обводки нет — рамка на каждой из двадцати с лишним пустых клеток
            # собирала бы обратно ту самую таблицу, от которой уходим.
            c.rrect(cx1, cy1, cx2, cy2, T["radius_cell"], fill=T["surface_secondary"])
            c.text(day_numbers[idx], cx1 + 13, cy1 + 11, f_day_off,
                   T["weekend"] if weekend else T["text_muted"])

    # ── легенда ───────────────────────────────────────────────────────
    if used_codes:
        c.rrect(PAD, y_leg, W - PAD, y_leg + legend_h, T["radius_card"], fill=T["surface"])
        f_code = c.font("bold", 17)
        f_title = c.font("regular", 17)
        ly = y_leg + CPAD
        for code in used_codes:
            pal = SALON_PALETTE.get(code, SALON_FALLBACK)
            c.dot(grid_x + 5, ly + 13, 5, pal["primary"])
            c.text(code, grid_x + 24, ly + 3, f_code, T["text"])
            title = _ru_quotes((info.get(code, {}) or {}).get("name", ""))
            if title:
                tx = grid_x + 24 + max(c.text_w(code, f_code), 34) + 16
                c.text(c.ellipsize(title, f_title, W - PAD - CPAD - tx),
                       tx, ly + 3, f_title, T["text_secondary"])
            ly += T["legend_row_h"]

    filename = f"schedule_{employee_name}.png"
    c.save(filename)
    log(f"✅ [create_schedule_image] Файл создан: {filename}")
    return filename


# ── Расчётный лист ────────────────────────────────────────────────────────
#
# Та же система, что и у расписания: холст 1080, светлый холодный фон, белые
# карточки со скруглением 24, мягкие тени, Segoe UI. Акцент другой — синий
# против фиолетового у расписания: два документа должны отличаться с одного
# взгляда, оставаясь одной системой.
PAYROLL_THEME = {
    "width": 1080,
    "scale": 2,

    "background":        "#F4F5F8",
    "surface":           "#FFFFFF",
    "surface_secondary": "#F7F8FB",
    "border":            "#E4E6EC",
    "text":              "#202124",
    "text_secondary":    "#737784",
    "text_muted":        "#A7ABB6",

    "primary":           "#5274E8",
    "primary_soft":      "#EEF2FF",
    "positive":          "#2B9A6A",
    "positive_soft":     "#E8F6F0",
    "negative":          "#B94A48",
    "negative_soft":     "#FCEEEE",
    "orange":            "#B87820",
    "progress_track":    "#E5E8EF",

    "radius_card":       24,
    "radius_inner":      18,

    "shadow_color":      (24, 26, 42),
    "shadow_alpha":      22,
    "shadow_blur":       11,
    "shadow_dy":         5,

    "page_pad":          32,
    "card_pad":          28,
    "gap":               16,

    "row_h":             40,        # строка начислений
    "kpi_gap":           26,
}


def _amount_value(s: str) -> int:
    """Число из отформатированной суммы. 0, если цифр нет."""
    digits = re.sub(r"[^\d]", "", s or "")
    return int(digits) if digits else 0


def _is_negative(s: str) -> bool:
    return bool(s) and ("−" in s or s.strip().startswith("-"))


def create_payroll_report_image(sections: list, filename: str = "salary_report.png"):
    """Расчётный лист сотрудника — экраном финансового приложения.

    Ожидает ту же структуру, что возвращает generate_employee_report_from_payroll():
    три секции — шапка, KPI, начисления с удержаниями. Ни разбор, ни суммы,
    ни формулы здесь не трогаются, переработан только визуальный слой.

    Порядок блоков отвечает вопросу, ради которого лист открывают: сколько я
    получу. Сумма к выплате стоит первой и крупнее всего на картинке, под ней
    одной строкой начислено и удержано. Дальше — расшифровка начислений,
    удержания и выполнение плана.
    """
    T = PAYROLL_THEME
    W = T["width"]
    PAD, CPAD, GAP = T["page_pad"], T["card_pad"], T["gap"]
    IX = PAD + CPAD
    RX = W - PAD - CPAD

    # ── разбор входной структуры (не меняется) ────────────────────────
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
    rate_lines = []
    if mr and mr != "—":
        # Было «× 15 см» — сокращение читалось как сантиметры.
        rate_lines.append(f"Осн. {mr} × {ms} {_shifts_word(ms)}")
    if er and er != "—":
        rate_lines.append(f"доп. {er} × {es} {_shifts_word(es)}")

    def parse_kpi(s):
        if not s or s.strip() == "—":
            return None
        lines = s.split("\n")
        # Принудительный режим: план не считался вовсе, и строки идут иначе.
        # Разбирать их как обычные — значит взять «7» из «✅ 7%, комиссия:
        # 35 791 ₽» за план, а саму комиссию за факт, получив выполнение
        # 5113 %. Такой KPI показываем без полосы: сравнивать не с чем.
        if "Принудительно" in lines[0]:
            m = re.search(r'(\d+)%', lines[1] if len(lines) > 1 else "")
            return dict(
                forced="макс." if "макс" in lines[0] else "мин.",
                met="✅" in (lines[1] if len(lines) > 1 else ""),
                rate=m.group(0) if m else "",
                plan=0.0, fact=0.0, fulfillment=0.0,
                detail=lines[2] if len(lines) > 2 else "",
                extra="",
            )
        met = "✅" in lines[0]
        m = re.search(r'(\d+)%', lines[0])
        rate = m.group(0) if m else ""
        plan = fact = 0.0
        if len(lines) > 1:
            nums = re.findall(r'[\d ]+', lines[1])
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
        elif key in {"Удержание", "Аванс"}:
            # Нулевое удержание — это отсутствие удержания, а не строка отчёта.
            if _amount_value(val):
                deductions.append((key, val))
        else:
            charges.append((key, val))

    held = sum(_amount_value(v) for _, v in deductions)
    held_str = f"{held:,} ₽".replace(",", " ")
    negative_net = _is_negative(net_pay)

    # ── высоты блоков ─────────────────────────────────────────────────
    HERO_TOP = 136                     # имя + период
    HERO_PILL = 116                    # «К выплате» и сумма
    HERO_SUM = 58 if (total or held) else 0
    hero_h = HERO_TOP + HERO_PILL + HERO_SUM + CPAD - 8

    HEAD_H = 58                        # заголовок карточки и отступ под ним
    charges_h = (CPAD + HEAD_H + len(charges) * T["row_h"] + 22 + 46 + CPAD - 10) if charges else 0
    ded_h = (CPAD + HEAD_H + len(deductions) * T["row_h"] + CPAD - 12) if deductions else 92

    KPI_FULL = 128                     # с полосой выполнения
    KPI_FORCED = 84
    KPI_NONE = 52
    kpi_h = 0
    if kpi_parsed:
        kpi_h = CPAD + HEAD_H
        for i, (_, p) in enumerate(kpi_parsed):
            kpi_h += KPI_NONE if p is None else (KPI_FORCED if p["forced"] else KPI_FULL)
            if i < len(kpi_parsed) - 1:
                kpi_h += T["kpi_gap"]
        kpi_h += CPAD - 8

    blocks = [hero_h] + [h for h in (charges_h, ded_h, kpi_h) if h]
    H = PAD + sum(blocks) + GAP * (len(blocks) - 1) + PAD

    c = _Canvas(W, H, T["background"], T["scale"])

    # тени всех карточек одним слоем, до самих карточек
    ys, boxes = PAD, []
    for bh in blocks:
        boxes.append((PAD, ys, W - PAD, ys + bh, T["radius_card"]))
        ys += bh + GAP
    c.shadow(boxes, T["shadow_color"], T["shadow_alpha"], T["shadow_blur"], T["shadow_dy"])

    def card(y, h):
        c.rrect(PAD, y, W - PAD, y + h, T["radius_card"],
                fill=T["surface"], outline=T["border"], width=1)

    def heading(s, y, color=None):
        c.text(s, IX, y, c.font("semibold", 24), color or T["text"])

    y = PAD

    # ── 1. Главный финансовый блок ────────────────────────────────────
    card(y, hero_h)

    parts = name.strip().rsplit(" ", 1)
    if len(parts) == 2 and parts[1].isdigit():
        base_name, tab_no = parts[0], parts[1]
    else:
        base_name, tab_no = name.strip(), ""
    f_name = c.fit_font(name.strip() or "—", "bold", 42, RX - IX, 24)
    c.text(base_name, IX, y + 34, f_name, T["text"])
    if tab_no:
        c.text(" " + tab_no, IX + c.text_w(base_name, f_name), y + 34,
               f_name, T["primary"])
    c.tracked(f"{period.upper()} · РАСЧЁТ ЗАРПЛАТЫ", IX, y + 92,
              c.font("semibold", 16), T["text_secondary"], 1.4)

    # Сумма к выплате — самый заметный элемент листа. Отрицательная получает
    # мягкую подложку: она означает, что аванс уже перекрыл начисленное, и
    # человек должен это заметить, но кричать об этом красным блоком незачем.
    pay_y = y + HERO_TOP
    accent = T["negative"] if negative_net else T["primary"]
    f_label = c.font("regular", 19)
    f_pay = c.fit_font(net_pay or "—", "bold", 62, RX - IX - 40, 34)
    if negative_net:
        # Плашка обнимает содержимое, а не тянется во всю карточку: красным
        # здесь помечают факт, а не подают тревогу.
        pill_w = max(c.text_w("К выплате", f_label),
                     c.text_w(net_pay or "—", f_pay)) + 44
        c.rrect(IX - 20, pay_y, IX - 20 + min(pill_w, RX - IX + 40),
                pay_y + HERO_PILL, T["radius_inner"], fill=T["negative_soft"])
    c.text("К выплате", IX, pay_y + 16, f_label, T["text_secondary"])
    c.text(net_pay or "—", IX, pay_y + 44, f_pay, accent)

    if HERO_SUM:
        sy = pay_y + HERO_PILL + 18
        c.line(IX, sy, RX, T["border"])
        f_sum = c.font("regular", 17)
        f_sum_b = c.font("semibold", 17)
        x = IX
        if total:
            c.text(total, x, sy + 14, f_sum_b, T["text"])
            x += c.text_w(total, f_sum_b) + 8
            c.text("начислено", x, sy + 14, f_sum, T["text_secondary"])
            x += c.text_w("начислено", f_sum) + 18
        if held:
            c.text("·", x, sy + 14, f_sum, T["text_muted"])
            x += 16
            c.text(held_str, x, sy + 14, f_sum_b, T["negative"])
            x += c.text_w(held_str, f_sum_b) + 8
            c.text("удержано", x, sy + 14, f_sum, T["text_secondary"])
    y += hero_h + GAP

    # ── 2. Начисления ─────────────────────────────────────────────────
    if charges:
        card(y, charges_h)
        heading("Начисления", y + CPAD)
        # Ставки и смены — контекст к окладу, а не отдельный показатель:
        # мельче заголовка и прижаты вправо, чтобы с ним не спорить.
        f_ctx = c.font("regular", 15)
        for i, ln in enumerate(rate_lines):
            c.text(ln, RX, y + CPAD + 2 + i * 21, f_ctx, T["text_secondary"], anchor="ra")

        f_key = c.font("regular", 19)
        f_val = c.font("semibold", 19)
        ry = y + CPAD + HEAD_H
        for key, val in charges:
            c.text(key, IX, ry, f_key, T["text_secondary"])
            # Нулевая строка не врёт, но и внимания не просит.
            c.text(val, RX, ry, f_val,
                   T["text"] if _amount_value(val) else T["text_muted"], anchor="ra")
            ry += T["row_h"]
        if total:
            ry += 6
            c.line(IX, ry, RX, T["border"])
            c.text("Итого", IX, ry + 16, c.font("semibold", 21), T["text"])
            c.text(total, RX, ry + 13, c.font("bold", 25), T["text"], anchor="ra")
        y += charges_h + GAP

    # ── 3. Удержано ───────────────────────────────────────────────────
    card(y, ded_h)
    heading("Удержано", y + CPAD, T["negative"])
    if deductions:
        f_key = c.font("regular", 19)
        f_val = c.font("semibold", 19)
        ry = y + CPAD + HEAD_H
        for key, val in deductions:
            c.text(key, IX, ry, f_key, T["text_secondary"])
            c.text("− " + val, RX, ry, f_val, T["negative"], anchor="ra")
            ry += T["row_h"]
    else:
        # Пустая карточка в полный рост ради одного нуля — шум. Ноль встаёт
        # в строку с заголовком.
        c.text("0 ₽", RX, y + CPAD - 2, c.font("semibold", 22),
               T["text_muted"], anchor="ra")
    y += ded_h + GAP

    # ── 4. Выполнение плана ───────────────────────────────────────────
    if kpi_parsed:
        card(y, kpi_h)
        heading("Выполнение плана", y + CPAD)
        ky = y + CPAD + HEAD_H
        f_name_k = c.font("semibold", 20)
        f_rate = c.font("regular", 15)
        f_detail = c.font("regular", 16)
        for i, (kn, p) in enumerate(kpi_parsed):
            if p is None:
                c.text(kn, IX, ky, f_name_k, T["text"])
                c.text("план не ставился", RX, ky + 2, f_detail,
                       T["text_muted"], anchor="ra")
                ky += KPI_NONE
            elif p["forced"]:
                col = T["positive"] if p["met"] else T["orange"]
                c.text(kn, IX, ky, f_name_k, T["text"])
                tag = f"принудительно: {p['forced']}"
                c.text(tag, RX, ky + 2, f_detail, col, anchor="ra")
                if p["rate"]:
                    c.text(f"ставка {p['rate']}", RX - c.text_w(tag, f_detail) - 14,
                           ky + 4, f_rate, T["text_secondary"], anchor="ra")
                if p["detail"]:
                    c.text(p["detail"], IX, ky + 34, f_detail, T["text_secondary"])
                ky += KPI_FORCED
            else:
                col = T["positive"] if p["met"] else T["orange"]
                pct = int(round(p["fulfillment"] * 100)) if p["plan"] else 0
                c.text(kn, IX, ky, f_name_k, T["text"])
                # Справа два числа: выполнение крупно и цветом, ставка
                # комиссии рядом и мельче. Раньше на этом месте стояла одна
                # ставка, и «7%» рядом с полосой читалось как выполнение.
                f_pct = c.font("bold", 21)
                pct_s = f"{pct}%"
                c.text(pct_s, RX, ky - 1, f_pct, col, anchor="ra")
                if p["rate"]:
                    c.text(f"ставка {p['rate']}", RX - c.text_w(pct_s, f_pct) - 14,
                           ky + 4, f_rate, T["text_secondary"], anchor="ra")
                c.bar(IX, ky + 36, RX - IX, 10, p["fulfillment"],
                      T["progress_track"], col)
                if p["detail"]:
                    c.text(p["detail"], IX, ky + 58, f_detail, T["text_secondary"])
                if p["extra"]:
                    c.text(p["extra"], IX, ky + 86, f_detail,
                           T["negative"] if "До 80%" in p["extra"] else T["positive"])
                ky += KPI_FULL
            if i < len(kpi_parsed) - 1:
                ky += T["kpi_gap"]

    c.save(filename)
    log(f"✅ [create_payroll_report_image] Saved: {filename}")
    return filename
