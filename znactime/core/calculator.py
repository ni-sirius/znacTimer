from dataclasses import replace
from datetime import date, datetime

from znactime.core.calendar_utils import calendar_week_tag, is_weekend
from znactime.core.models import DayEntry
from znactime.core.time_utils import hours_to_hhmm, interruption_hours


ROW_COLOR_KEYS = {
    "weekend": "weekend",
    "weekend_today": "weekend_today",
    "special_day": "special_day",
    "special_day_today": "special_day_today",
    "missing_times": "missing_times",
    "missing_times_today": "missing_times_today",
    "valid_day": "valid_day",
    "valid_day_today": "valid_day_today",
}


def _is_today(date_str, today):
    try:
        return datetime.strptime(date_str, "%d.%m.%Y").date() == today
    except ValueError:
        return False


def _calculate_worked_hours(start, end, interruption):
    start_time = datetime.strptime(start, "%H:%M")
    end_time = datetime.strptime(end, "%H:%M")

    if end_time <= start_time:
        raise ValueError("End must be after start")

    interruption_h = interruption_hours(interruption)
    return (end_time - start_time).total_seconds() / 3600 - interruption_h


def recalculate(
    entries: list[DayEntry],
    carry_over: float,
    day_hours: float,
    today: date,
    month_closed: bool,
) -> list[DayEntry]:
    calculated_entries = []
    monthly_balance = carry_over

    for entry in entries:
        daily_ot = 0.0
        row_color = ""
        special = entry.special
        entry_is_today = _is_today(entry.date, today)

        if is_weekend(entry.date):
            if special.lower() in ("", "normal day"):
                special = "Weekend"
            row_color = (
                ROW_COLOR_KEYS["weekend_today"]
                if entry_is_today
                else ROW_COLOR_KEYS["weekend"]
            )
        elif special and special.lower() != "normal day":
            row_color = (
                ROW_COLOR_KEYS["special_day_today"]
                if entry_is_today
                else ROW_COLOR_KEYS["special_day"]
            )
        elif entry.start == "00:00" or entry.end == "00:00":
            row_color = (
                ROW_COLOR_KEYS["missing_times_today"]
                if entry_is_today
                else ROW_COLOR_KEYS["missing_times"]
            )
        else:
            try:
                worked = _calculate_worked_hours(
                    entry.start,
                    entry.end,
                    entry.interruption,
                )
                daily_ot = worked - day_hours
                row_color = (
                    ROW_COLOR_KEYS["valid_day_today"]
                    if entry_is_today
                    else ROW_COLOR_KEYS["valid_day"]
                )
            except Exception:
                row_color = (
                    ROW_COLOR_KEYS["missing_times_today"]
                    if entry_is_today
                    else ROW_COLOR_KEYS["missing_times"]
                )

        if month_closed:
            row_color = (
                ROW_COLOR_KEYS["special_day_today"]
                if entry_is_today
                else ROW_COLOR_KEYS["special_day"]
            )

        monthly_balance += daily_ot

        calculated_entries.append(
            replace(
                entry,
                cw=calendar_week_tag(entry.date),
                special=special,
                daily_ot=hours_to_hhmm(daily_ot),
                monthly_balance=hours_to_hhmm(monthly_balance),
                row_color=row_color,
            )
        )

    return calculated_entries
