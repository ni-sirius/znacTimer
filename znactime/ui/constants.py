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
    "Monthly balance",
]

LIGHT_ROW_COLORS = {
    "weekend": "#e6ecff",
    "weekend_today": "#80b3ff",
    "special_day": "#dddddd",
    "special_day_today": "#999999",
    "missing_times": "#ffcccc",
    "missing_times_today": "#ff9999",
    "valid_day": "#ccffcc",
    "valid_day_today": "#99ff99",
}

DARK_ROW_COLORS = {
    "weekend": "#26324f",
    "weekend_today": "#315b96",
    "special_day": "#3a3a3a",
    "special_day_today": "#555555",
    "missing_times": "#5a2528",
    "missing_times_today": "#79363a",
    "valid_day": "#244a32",
    "valid_day_today": "#326b45",
}

COLORS = LIGHT_ROW_COLORS


def row_color_hex(row_color, dark=False):
    if not row_color:
        return ""
    if row_color.startswith("#"):
        return row_color

    palette = DARK_ROW_COLORS if dark else LIGHT_ROW_COLORS
    return palette.get(row_color, "")
