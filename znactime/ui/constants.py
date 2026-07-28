import calendar


MONTHS = list(calendar.month_name)[1:]

COLUMNS = [
    "CW",
    "Date",
    "Special day",
    "Start",
    "End",
    "Interruption",
    "Daily OT",
    "Monthly",
]

LIGHT_ROW_COLORS = {
    "weekend": "#e1edff",
    "weekend_today": "#bcd6ff",
    "special_day": "#eee6fa",
    "special_day_today": "#d5c4f0",
    "missing_times": "#fde4e9",
    "missing_times_today": "#f8c4ce",
    "valid_day": "#e0f5e8",
    "valid_day_today": "#bce8cc",
}

DARK_ROW_COLORS = {
    "weekend": "#2b3d5b",
    "weekend_today": "#3a5d8d",
    "special_day": "#3d3150",
    "special_day_today": "#594477",
    "missing_times": "#512e3a",
    "missing_times_today": "#743b4b",
    "valid_day": "#2a4938",
    "valid_day_today": "#396b4e",
}

COLORS = LIGHT_ROW_COLORS

LIGHT_CURRENT_ROW_ACCENT = "#6941c6"
DARK_CURRENT_ROW_ACCENT = "#c58af9"

LIGHT_OVERTIME_TEXT_COLORS = {
    "positive": "#18864b",
    "negative": "#c23b4d",
}

DARK_OVERTIME_TEXT_COLORS = {
    "positive": "#78d99c",
    "negative": "#ff8796",
}

LIGHT_CALENDAR_WEEK_TEXT_COLORS = ("#202124", "#8993a1")
DARK_CALENDAR_WEEK_TEXT_COLORS = ("#f1f3f4", "#7f8b9b")


def row_color_hex(row_color, dark=False):
    if not row_color:
        return ""
    if row_color.startswith("#"):
        return row_color

    palette = DARK_ROW_COLORS if dark else LIGHT_ROW_COLORS
    return palette.get(row_color, "")


def current_row_accent_hex(dark=False):
    return DARK_CURRENT_ROW_ACCENT if dark else LIGHT_CURRENT_ROW_ACCENT


def calendar_week_text_color_hex(calendar_week, dark=False):
    try:
        week_number = int(str(calendar_week).rsplit("-", 1)[-1])
    except (TypeError, ValueError):
        week_number = 1

    palette = (
        DARK_CALENDAR_WEEK_TEXT_COLORS
        if dark
        else LIGHT_CALENDAR_WEEK_TEXT_COLORS
    )
    return palette[(week_number + 1) % 2]


def overtime_text_color_hex(value, dark=False):
    try:
        if str(value).strip().startswith("-"):
            state = "negative"
        elif str(value).strip() not in ("", "00:00"):
            state = "positive"
        else:
            return ""
    except (AttributeError, TypeError):
        return ""

    palette = DARK_OVERTIME_TEXT_COLORS if dark else LIGHT_OVERTIME_TEXT_COLORS
    return palette[state]
