import calendar

from znactime.core.constants import DayStatus, ZERO_DURATION

MONTHS = list(calendar.month_name)[1:]

LIGHT_ROW_COLORS = {
    DayStatus.WEEKEND: "#e1edff",
    DayStatus.WEEKEND_TODAY: "#bcd6ff",
    DayStatus.SPECIAL_DAY: "#eee6fa",
    DayStatus.SPECIAL_DAY_TODAY: "#d5c4f0",
    DayStatus.MISSING_TIMES: "#fde4e9",
    DayStatus.MISSING_TIMES_TODAY: "#f8c4ce",
    DayStatus.VALID_DAY: "#e0f5e8",
    DayStatus.VALID_DAY_TODAY: "#bce8cc",
}

DARK_ROW_COLORS = {
    DayStatus.WEEKEND: "#2b3d5b",
    DayStatus.WEEKEND_TODAY: "#3a5d8d",
    DayStatus.SPECIAL_DAY: "#3d3150",
    DayStatus.SPECIAL_DAY_TODAY: "#594477",
    DayStatus.MISSING_TIMES: "#512e3a",
    DayStatus.MISSING_TIMES_TODAY: "#743b4b",
    DayStatus.VALID_DAY: "#2a4938",
    DayStatus.VALID_DAY_TODAY: "#396b4e",
}

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
        elif str(value).strip() not in ("", ZERO_DURATION):
            state = "positive"
        else:
            return ""
    except (AttributeError, TypeError):
        return ""

    palette = DARK_OVERTIME_TEXT_COLORS if dark else LIGHT_OVERTIME_TEXT_COLORS
    return palette[state]
