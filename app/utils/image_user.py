from PIL import Image, ImageDraw, ImageFont
import pandas as pd

COLORS = {
    "П": "#ADD8E6",  # голубой
    "Ц": "#8A2BE2",  # фиолетовый
    "А": "#FFFF00",  # желтый
    "М": "#008000",  # зеленый
    "Р": "#D2B48C",  # светло коричневый
    "Оз": "#FFA500",  # рыжий
    "Ох": "#0000FF",  # синий
    "default": "#FFFFFF",  # белый
}


def create_schedule_image(tables, filename="salary_report.png"):
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
        log("❌ Error: Empty list of tables provided!")
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

    log(f"Размеры изображения: ширина={img_width}, высота={img_height}")

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
                log(
                    f"❌ Error: row {row} has {len(row)} elements (expected 2). Skipping!"
                )
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


def create_schedule_image_user(data, employee_name, sheet_name):
    employee_row = data[data["ИМЯ"] == employee_name]
    if employee_row.empty:
        log(f"⚠️ Нет данных для сотрудника {employee_name}")
        return None

    last_day = None
    for day in ["31", "30", "29", "28"]:
        if day in data.columns:
            last_day = int(day)
            break

    if last_day is None:
        log("⚠️ Нет подходящего столбца дня месяца")
        return None

    days = [str(day) for day in range(1, last_day + 1)]

    cell_width, cell_height = 50, 40
    header_height = 40
    left_width = 150
    month_header_height = 30
    week_header_height = 30

    img_width = left_width + cell_width * len(days)
    img_height = (
        month_header_height
        + week_header_height
        + header_height * 2
        + cell_height
    )

    img = Image.new("RGB", (img_width, img_height), "white")
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except IOError:
        font = ImageFont.load_default()

    # Название месяца сверху
    draw.rectangle(
        [0, 0, img_width, month_header_height], fill="#E0E0E0", outline="black"
    )
    bbox = draw.textbbox((0, 0), sheet_name, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((img_width - w) / 2, (month_header_height - h) / 2),
        sheet_name,
        fill="black",
        font=font,
    )

    # Заголовки дней
    for i, day in enumerate(days):
        x0 = left_width + i * cell_width
        draw.rectangle(
            [
                x0,
                month_header_height,
                x0 + cell_width,
                month_header_height + header_height,
            ],
            fill="#D3D3D3",
            outline="black",
        )
        bbox = draw.textbbox((0, 0), day, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            (
                x0 + (cell_width - w) / 2,
                month_header_height + (header_height - h) / 2,
            ),
            day,
            font=font,
            fill="black",
        )

    # Дни недели
    weekdays = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"] * 5
    weekdays = weekdays[: len(days)]
    for i, weekday in enumerate(weekdays):
        x0 = left_width + i * cell_width
        draw.rectangle(
            [
                x0,
                month_header_height + header_height,
                x0 + cell_width,
                month_header_height + header_height * 2,
            ],
            fill="#A9A9A9",
            outline="black",
        )
        bbox = draw.textbbox((0, 0), weekday, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            (
                x0 + (cell_width - w) / 2,
                month_header_height + header_height + (header_height - h) / 2,
            ),
            weekday,
            font=font,
            fill="black",
        )

    # Имя сотрудника
    draw.rectangle(
        [0, month_header_height + header_height * 2, left_width, img_height],
        fill="#D3D3D3",
        outline="black",
    )
    bbox = draw.textbbox((0, 0), employee_name, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        (
            (left_width - w) / 2,
            month_header_height + header_height * 2 + (cell_height - h) / 2,
        ),
        employee_name,
        fill="black",
        font=font,
    )

    # Заполнение таблицы расписания
    for i, day in enumerate(days):
        x0 = left_width + i * cell_width
        y0 = month_header_height + header_height * 2
        val_str = (
            ""
            if pd.isna(employee_row.iloc[0][day])
            else str(employee_row.iloc[0][day])
        )
        color = COLORS.get(val_str, COLORS["default"])
        draw.rectangle(
            [x0, y0, x0 + cell_width, y0 + cell_height],
            fill=color,
            outline="black",
        )
        bbox = draw.textbbox((0, 0), val_str, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            (x0 + (cell_width - w) / 2, y0 + (cell_height - h) / 2),
            val_str,
            font=font,
            fill="black",
        )

    filename = f"schedule_{employee_name}.png"
    img.save(filename)

    return filename
