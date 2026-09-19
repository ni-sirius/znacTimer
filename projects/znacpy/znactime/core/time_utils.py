import re
from dataclasses import dataclass
from datetime import datetime

from znactime.core.constants import (
    INTERRUPTION_SEPARATOR,
    OPEN_END_MARKER,
    PERIOD_SEPARATOR,
    TIME_FORMAT,
    UNSET_TIME,
    ZERO_DURATION,
)


TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


@dataclass(frozen=True)
class InterruptionValue:
    normalized: str
    hours: float
    earliest_start: str | None = None
    latest_end: str | None = None
    has_incomplete: bool = False
    open_start: str | None = None


def coerce_time_input(value):
    value = str(value).strip()

    if value.isdigit():
        if len(value) == 4:
            hours, minutes = value[:2], value[2:]
        elif len(value) == 3:
            hours, minutes = "0" + value[0], value[1:]
        elif len(value) == 2:
            hours, minutes = "00", value
        elif len(value) == 1:
            hours, minutes = "00", "0" + value
        else:
            return None

        try:
            hour_value = int(hours)
            minute_value = int(minutes)
        except ValueError:
            return None

        if 0 <= hour_value <= 23 and 0 <= minute_value <= 59:
            value = f"{hour_value:02d}:{minute_value:02d}"
        else:
            return None

    if not TIME_RE.match(value):
        return None
    return value


def _minutes_from_hhmm(value):
    parsed = datetime.strptime(value, TIME_FORMAT)
    return parsed.hour * 60 + parsed.minute


def parse_interruption_input(value):
    value = str(value).strip()
    if not value:
        value = ZERO_DURATION

    if PERIOD_SEPARATOR not in value:
        normalized = coerce_time_input(value)
        if normalized is None:
            return None
        return InterruptionValue(
            normalized=normalized,
            hours=hhmm_to_hours(normalized),
        )

    periods = []
    incomplete_count = 0
    for raw_period in value.split(INTERRUPTION_SEPARATOR):
        raw_period = raw_period.strip()
        if raw_period.count(PERIOD_SEPARATOR) != 1:
            return None

        raw_start, raw_end = raw_period.split(PERIOD_SEPARATOR)
        start = coerce_time_input(raw_start.strip())
        end_text = raw_end.strip()
        end = None if end_text == OPEN_END_MARKER else coerce_time_input(end_text)
        if start is None or (end is None and end_text != OPEN_END_MARKER):
            return None

        start_minutes = _minutes_from_hhmm(start)
        end_minutes = None if end is None else _minutes_from_hhmm(end)
        if end is None:
            incomplete_count += 1
        periods.append(
            (start_minutes, end_minutes, start, end or OPEN_END_MARKER)
        )

    if incomplete_count > 1:
        return None

    periods.sort(key=lambda period: period[0])

    valid_periods = [
        period
        for period in periods
        if period[1] is None or period[1] > period[0]
    ]
    total_minutes = sum(
        max(0, end - start)
        for start, end, _start, _end in periods
        if end is not None
    )
    completed_ends = [
        (end_minutes, end)
        for _start_minutes, end_minutes, _start, end in periods
        if end_minutes is not None and end_minutes > _start_minutes
    ]
    return InterruptionValue(
        normalized=INTERRUPTION_SEPARATOR.join(
            f"{start}{PERIOD_SEPARATOR}{end}"
            for _start_minutes, _end_minutes, start, end in periods
        ),
        hours=total_minutes / 60,
        earliest_start=valid_periods[0][2] if valid_periods else None,
        latest_end=max(completed_ends)[1] if completed_ends else None,
        has_incomplete=bool(incomplete_count),
        open_start=next(
            (
                start
                for _start_minutes, end_minutes, start, _end in periods
                if end_minutes is None
            ),
            None,
        ),
    )


def coerce_interruption_input(value):
    parsed = parse_interruption_input(value)
    return None if parsed is None else parsed.normalized


def time_input_or_zero(value):
    return coerce_time_input(value) or UNSET_TIME


def interruption_input_or_zero(value):
    return coerce_interruption_input(value) or ZERO_DURATION


def open_interruption_start(value):
    """Return the start of the single open interruption, if present."""
    parsed = parse_interruption_input(value)
    return None if parsed is None else parsed.open_start


def is_open_interruption_period(value):
    """Return whether a normalized interruption period has an open end."""
    suffix = f"{PERIOD_SEPARATOR}{OPEN_END_MARKER}"
    return str(value).strip().endswith(suffix)


def interruption_hours(value):
    parsed = parse_interruption_input(value)
    if parsed is None:
        raise ValueError("Invalid interruption value")
    return parsed.hours


def expected_end_time(start, interruption, workday_hours):
    """Return a display-only expected end time for a started workday."""
    start = coerce_time_input(start)
    parsed_interruption = parse_interruption_input(interruption)
    if start in (None, UNSET_TIME) or parsed_interruption is None:
        return None

    start_minutes = _minutes_from_hhmm(start)
    workday_minutes = round(float(workday_hours) * 60)
    interruption_minutes = round(parsed_interruption.hours * 60)
    if workday_minutes <= 0:
        return None

    expected_minutes = (
        start_minutes + workday_minutes + interruption_minutes
    ) % (24 * 60)
    return f"{expected_minutes // 60:02d}:{expected_minutes % 60:02d}"


def interruption_has_outside_workday_period(value, workday_start, workday_end):
    """Return whether any explicit pause period exceeds workday boundaries."""
    parsed = parse_interruption_input(value)
    workday_start = coerce_time_input(workday_start)
    workday_end = coerce_time_input(workday_end)
    if (
        parsed is None
        or workday_start in (None, UNSET_TIME)
        or workday_end in (None, UNSET_TIME)
    ):
        return False
    if PERIOD_SEPARATOR not in parsed.normalized:
        return False

    for period in parsed.normalized.split(INTERRUPTION_SEPARATOR):
        period_start, period_end = period.split(PERIOD_SEPARATOR, 1)
        if period_start < workday_start:
            return True
        if period_end == OPEN_END_MARKER:
            if period_start >= workday_end:
                return True
            continue
        if period_end <= period_start or period_end > workday_end:
            return True
    return False


def append_interruption_period(value, start, end):
    period = f"{start}{PERIOD_SEPARATOR}{end}"
    existing = str(value).strip()
    if existing in ("", ZERO_DURATION):
        combined = period
    elif PERIOD_SEPARATOR in existing:
        combined = f"{existing}{INTERRUPTION_SEPARATOR}{period}"
    else:
        raise ValueError(
            "A duration interruption must be replaced before periods can be added"
        )

    parsed = parse_interruption_input(combined)
    if parsed is None:
        raise ValueError("The interruption period is invalid")
    return parsed.normalized


def finish_interruption_period(value, start, end):
    start = coerce_time_input(start)
    end = coerce_time_input(end)
    if start is None or end is None:
        raise ValueError("The interruption period is invalid")

    parsed = parse_interruption_input(value)
    if parsed is None:
        raise ValueError("The interruption period is invalid")
    if PERIOD_SEPARATOR not in parsed.normalized:
        if parsed.normalized == ZERO_DURATION:
            if end <= start:
                return parsed.normalized
            return append_interruption_period(parsed.normalized, start, end)
        raise ValueError("The interruption period is invalid")

    periods = parsed.normalized.split(INTERRUPTION_SEPARATOR)
    open_period = f"{start}{PERIOD_SEPARATOR}{OPEN_END_MARKER}"
    try:
        period_index = periods.index(open_period)
    except ValueError:
        if end <= start:
            return parsed.normalized
        return append_interruption_period(parsed.normalized, start, end)

    if end <= start:
        periods.pop(period_index)
    else:
        periods[period_index] = f"{start}{PERIOD_SEPARATOR}{end}"

    candidate = INTERRUPTION_SEPARATOR.join(periods) or ZERO_DURATION
    finished = parse_interruption_input(candidate)
    if finished is None:
        raise ValueError("The interruption period is invalid")
    return finished.normalized


def hhmm_to_hours(hhmm_str):
    if not hhmm_str or ":" not in hhmm_str:
        return 0.0
    try:
        is_negative = hhmm_str.strip().startswith("-")
        clean_str = hhmm_str.replace("-", "")
        hours_str, minutes_str = clean_str.split(":", 1)
        decimal_hours = int(hours_str) + int(minutes_str) / 60
        return -decimal_hours if is_negative else decimal_hours
    except (ValueError, AttributeError):
        return 0.0


def hours_to_hhmm(decimal_hours):
    is_negative = decimal_hours < 0
    abs_hours = abs(decimal_hours)

    hours = int(abs_hours)
    minutes = round((abs_hours - hours) * 60)

    if minutes == 60:
        hours += 1
        minutes = 0

    formatted_time = f"{hours:02d}:{minutes:02d}"
    return f"-{formatted_time}" if is_negative else formatted_time
