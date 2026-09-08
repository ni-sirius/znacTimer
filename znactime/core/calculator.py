from dataclasses import replace
from datetime import date, datetime

from znactime.core.calendar_utils import calendar_week_tag
from znactime.core.constants import (
    DATE_FORMAT,
    DayStatus,
    TIME_FORMAT,
    UNSET_TIME,
    WEEKEND_DAY,
    is_normal_day,
)
from znactime.core.models import DayEntry
from znactime.core.time_utils import (
    hhmm_to_hours,
    hours_to_hhmm,
    interruption_has_outside_workday_period,
    interruption_input_or_zero,
    interruption_hours,
    parse_interruption_input,
    time_input_or_zero,
)


def _normalize_entry(entry: DayEntry) -> DayEntry:
    return replace(
        entry,
        start=time_input_or_zero(entry.start),
        end=time_input_or_zero(entry.end),
        interruption=interruption_input_or_zero(entry.interruption),
        special=str(entry.special or ""),
    )


def _calendar_context(date_text: str, today: date) -> tuple[str, bool, bool]:
    try:
        entry_date = datetime.strptime(date_text, DATE_FORMAT).date()
        return calendar_week_tag(date_text), entry_date == today, True
    except (TypeError, ValueError):
        return "", False, False


def _calculate_worked_hours(start: str, end: str, interruption: str) -> float:
    start_time = datetime.strptime(start, TIME_FORMAT)
    end_time = datetime.strptime(end, TIME_FORMAT)
    if end_time <= start_time:
        raise ValueError("End must be after start")
    return (
        (end_time - start_time).total_seconds() / 3600
        - interruption_hours(interruption)
    )


def _calculate_daily_overtime(
    entry: DayEntry,
    *,
    day_hours: float,
    date_is_valid: bool,
) -> tuple[float, bool]:
    """Return daily overtime and whether normal-day time data is incomplete."""
    if not date_is_valid:
        return 0.0, True

    if entry.start == UNSET_TIME or entry.end == UNSET_TIME:
        expected_minutes = (
            entry.expected_work_minutes
            if entry.expected_work_minutes is not None
            else round(day_hours * 60)
        )
        return 0.0, expected_minutes != 0

    try:
        interruption = parse_interruption_input(entry.interruption)
        worked = _calculate_worked_hours(
            entry.start,
            entry.end,
            entry.interruption,
        )
        interruption_is_invalid = (
            interruption is None
            or interruption.has_incomplete
            or interruption_has_outside_workday_period(
                entry.interruption,
                entry.start,
                entry.end,
            )
            or worked < 0
        )
        if interruption_is_invalid:
            return 0.0, True
        expected_hours = (
            entry.expected_work_minutes / 60
            if entry.expected_work_minutes is not None
            else day_hours
        )
        return worked - expected_hours, False
    except Exception:
        return 0.0, True


def _today_variant(regular: str, current: str, entry_is_today: bool) -> str:
    return current if entry_is_today else regular


def _assign_row_color(
    entry: DayEntry,
    *,
    entry_is_today: bool,
    date_is_valid: bool,
    time_data_is_incomplete: bool,
    month_closed: bool,
) -> str:
    """Assign presentation state without changing any calculated value."""
    special = str(entry.special or "").strip()
    if special.casefold() == WEEKEND_DAY.casefold():
        return _today_variant(
            DayStatus.WEEKEND,
            DayStatus.WEEKEND_TODAY,
            entry_is_today,
        )
    if not is_normal_day(special):
        return _today_variant(
            DayStatus.SPECIAL_DAY,
            DayStatus.SPECIAL_DAY_TODAY,
            entry_is_today,
        )
    if month_closed:
        return _today_variant(
            DayStatus.SPECIAL_DAY,
            DayStatus.SPECIAL_DAY_TODAY,
            entry_is_today,
        )
    if not date_is_valid or time_data_is_incomplete:
        return _today_variant(
            DayStatus.MISSING_TIMES,
            DayStatus.MISSING_TIMES_TODAY,
            entry_is_today,
        )
    return _today_variant(
        DayStatus.VALID_DAY,
        DayStatus.VALID_DAY_TODAY,
        entry_is_today,
    )


def _advance_open_month_balance(
    daily_overtime: float,
    monthly_balance: float,
) -> tuple[str, str, float]:
    """Advance the balance using exactly the finalized Daily OT text value."""
    daily_overtime_text = hours_to_hhmm(daily_overtime)
    monthly_balance += hhmm_to_hours(daily_overtime_text)
    return (
        daily_overtime_text,
        hours_to_hhmm(monthly_balance),
        monthly_balance,
    )


def _result_values(
    entry: DayEntry,
    *,
    daily_overtime: float,
    monthly_balance: float,
    month_closed: bool,
) -> tuple[str, str, float]:
    if month_closed and entry.daily_ot and entry.monthly_balance:
        return (
            entry.daily_ot,
            entry.monthly_balance,
            hhmm_to_hours(entry.monthly_balance),
        )
    return _advance_open_month_balance(daily_overtime, monthly_balance)


def _recalculate_entry(
    entry: DayEntry,
    *,
    monthly_balance: float,
    day_hours: float,
    today: date,
    month_closed: bool,
) -> tuple[DayEntry, float]:
    normalized = _normalize_entry(entry)
    cw, entry_is_today, date_is_valid = _calendar_context(normalized.date, today)
    daily_overtime, time_data_is_incomplete = _calculate_daily_overtime(
        normalized,
        day_hours=day_hours,
        date_is_valid=date_is_valid,
    )
    row_color = _assign_row_color(
        normalized,
        entry_is_today=entry_is_today,
        date_is_valid=date_is_valid,
        time_data_is_incomplete=time_data_is_incomplete,
        month_closed=month_closed,
    )
    daily_text, monthly_text, monthly_balance = _result_values(
        normalized,
        daily_overtime=daily_overtime,
        monthly_balance=monthly_balance,
        month_closed=month_closed,
    )
    return (
        replace(
            normalized,
            cw=cw,
            daily_ot=daily_text,
            monthly_balance=monthly_text,
            row_color=row_color,
        ),
        monthly_balance,
    )


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
        calculated, monthly_balance = _recalculate_entry(
            entry,
            monthly_balance=monthly_balance,
            day_hours=day_hours,
            today=today,
            month_closed=month_closed,
        )
        calculated_entries.append(calculated)
    return calculated_entries
