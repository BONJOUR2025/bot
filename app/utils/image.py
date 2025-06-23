from PIL import Image, ImageDraw, ImageFont
import pandas as pd
import os
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


def create_combined_table_image(tables, filename="salary_report.png"):
    """
    Генерирует изображение с таблицами отчёта.
    Заголовки таблиц центрируются, ключи выравниваются вправо, значения — влево.
    """
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except IOError:
        font = ImageFont.load_default()

    padding = 40
    column_spacing = 20
    row_height = 40
    header_height = 50
    line_spacing = 15

    if not tables or all(len(table) < 2 for table in tables):
        print("❌ Error: Empty list of tables provided!")
        return None

    key_lengths = [
        len(row[0]) for table in tables for row in table[1:] if len(row) == 2
    ]
    value_lengths = [
        max(len(line) for line in row[1].split("\n"))
        for table in tables
        for row in table[1:]
        if len(row) == 2
    ]

    max_key_width = max(key_lengths) * 12 if key_lengths else 100
    max_value_width = max(value_lengths) * 12 if value_lengths else 100

    total_height = (
        sum(
            (
                header_height
                + sum(
                    (len(row[1].split("\n")) if len(row) == 2 else 1)
                    * row_height
                    for row in table[1:]
                )
            )
            for table in tables
        )
        + padding
    )

    img_width = (
        max_key_width + column_spacing + max_value_width + (2 * padding)
    )
    img_height = total_height

    print(f"Размеры изображения: ширина={img_width}, высота={img_height}")

    img = Image.new("RGB", (img_width, img_height), "white")
    draw = ImageDraw.Draw(img)
    y_offset = padding

    for table in tables:
        draw.rectangle(
            [
                (padding, y_offset),
                (img_width - padding, y_offset + header_height),
            ],
            fill="lightgray",
            outline="black",
        )
        text_width = draw.textlength(table[0][0], font=font)
        draw.text(
            ((img_width - text_width) / 2, y_offset + 15),
            table[0][0],
            fill="black",
            font=font,
        )
        y_offset += header_height

        for row in table[1:]:
            if len(row) != 2:
                print(
                    f"❌ Error: row {row} has {
                        len(row)} elements (expected 2). Skipping!")
                continue
            key, value = row
            value_lines = value.split("\n")
            key_x = padding + max_key_width - draw.textlength(key, font=font)
            value_x = padding + max_key_width + column_spacing
            draw.line(
                [(padding, y_offset), (img_width - padding, y_offset)],
                fill="black",
                width=2,
            )
            draw.text((key_x, y_offset + 10), key, fill="black", font=font)
            draw.text(
                (value_x, y_offset + 10),
                value_lines[0],
                fill="black",
                font=font,
            )
            y_offset += row_height
            for line in value_lines[1:]:
                draw.text((value_x, y_offset), line, fill="black", font=font)
                y_offset += row_height - line_spacing
        draw.line(
            [(padding, y_offset), (img_width - padding, y_offset)],
            fill="black",
            width=3,
        )
        y_offset += 15

    img.save(filename)
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
        f"DEBUG [create_schedule_image] Данные сотрудника: {
            employee_row.to_dict()}")

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
