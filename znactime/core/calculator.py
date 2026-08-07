from dataclasses import replace
from datetime import date, datetime

from znactime.core.calendar_utils import calendar_week_tag, is_weekend
from znactime.core.constants import (
    DATE_FORMAT,
    DayStatus,
    NORMAL_DAY,
    TIME_FORMAT,
    UNSET_TIME,
    WEEKEND_DAY,
)
from znactime.core.models import DayEntry
from znactime.core.time_utils import (
    hours_to_hhmm,
    interruption_has_outside_workday_period,
    interruption_input_or_zero,
    interruption_hours,
    parse_interruption_input,
    time_input_or_zero,
)

def _is_today(date_str, today):
    try:
        return datetime.strptime(date_str, DATE_FORMAT).date() == today
    except (TypeError, ValueError):
        return False


def _calculate_worked_hours(start, end, interruption):
    start_time = datetime.strptime(start, TIME_FORMAT)
    end_time = datetime.strptime(end, TIME_FORMAT)

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
        entry = replace(
            entry,
            start=time_input_or_zero(entry.start),
            end=time_input_or_zero(entry.end),
            interruption=interruption_input_or_zero(entry.interruption),
        )
        daily_ot = 0.0
        row_color = ""
        special = str(entry.special or "")
        entry_is_today = _is_today(entry.date, today)
        try:
            cw = calendar_week_tag(entry.date)
            entry_is_weekend = is_weekend(entry.date)
            date_is_valid = True
        except (TypeError, ValueError):
            cw = ""
            entry_is_weekend = False
            date_is_valid = False

        if not date_is_valid:
            row_color = DayStatus.MISSING_TIMES
        elif entry_is_weekend:
            if special.casefold() in ("", NORMAL_DAY.casefold()):
                special = WEEKEND_DAY
            row_color = (
                DayStatus.WEEKEND_TODAY
                if entry_is_today
                else DayStatus.WEEKEND
            )
        elif special and special.casefold() != NORMAL_DAY.casefold():
            row_color = (
                DayStatus.SPECIAL_DAY_TODAY
                if entry_is_today
                else DayStatus.SPECIAL_DAY
            )

        if not date_is_valid:
            daily_ot = 0.0
        elif entry.start == UNSET_TIME or entry.end == UNSET_TIME:
            if row_color:
                daily_ot = 0.0
            else:
                row_color = (
                    DayStatus.MISSING_TIMES_TODAY
                    if entry_is_today
                    else DayStatus.MISSING_TIMES
                )
        else:
            try:
                worked = _calculate_worked_hours(
                    entry.start,
                    entry.end,
                    entry.interruption,
                )
                daily_ot = worked - day_hours
                interruption = parse_interruption_input(entry.interruption)
                interruption_is_invalid = (
                    interruption.has_incomplete
                    or interruption_has_outside_workday_period(
                        entry.interruption,
                        entry.start,
                        entry.end,
                    )
                )
                if not row_color and interruption_is_invalid:
                    row_color = (
                        DayStatus.MISSING_TIMES_TODAY
                        if entry_is_today
                        else DayStatus.MISSING_TIMES
                    )
                elif not row_color:
                    row_color = (
                        DayStatus.VALID_DAY_TODAY
                        if entry_is_today
                        else DayStatus.VALID_DAY
                    )
            except Exception:
                row_color = (
                    DayStatus.MISSING_TIMES_TODAY
                    if entry_is_today
                    else DayStatus.MISSING_TIMES
                )

        if month_closed:
            row_color = (
                DayStatus.SPECIAL_DAY_TODAY
                if entry_is_today
                else DayStatus.SPECIAL_DAY
            )

        monthly_balance += daily_ot

        calculated_entries.append(
            replace(
                entry,
                cw=cw,
                special=special,
                daily_ot=hours_to_hhmm(daily_ot),
                monthly_balance=hours_to_hhmm(monthly_balance),
                row_color=row_color,
            )
        )

    return calculated_entries
