from __future__ import annotations

from datetime import date, datetime

from znactime.core.calendar_utils import calendar_week_tag
from znactime.core.constants import NORMAL_DAY, OPEN_END_MARKER, ZERO_DURATION
from znactime.core.models import BreakRecord, DayEntry, DayRecord


def minute_text(value: int | None) -> str:
    if value is None:
        return "00:00"
    return f"{value // 60:02d}:{value % 60:02d}"


def signed_minute_text(value: int | None) -> str:
    if value is None:
        return ""
    prefix = "-" if value < 0 else ""
    absolute = abs(value)
    return f"{prefix}{absolute // 60:02d}:{absolute % 60:02d}"


def parse_display_date(value: str) -> date:
    return datetime.strptime(value, "%d.%m.%Y").date()


def parse_clock(value: str) -> int | None:
    token = str(value).strip()
    if token in ("", "00:00"):
        return None
    parsed = datetime.strptime(token, "%H:%M")
    return parsed.hour * 60 + parsed.minute


def day_record_to_entry(record: DayRecord) -> DayEntry:
    date_text = record.work_date.strftime("%d.%m.%Y")
    if record.breaks:
        interruption = ";".join(
            f"{minute_text(item.start_minute)}-"
            f"{OPEN_END_MARKER if item.end_minute is None else minute_text(item.end_minute)}"
            for item in record.breaks
        )
    elif record.break_duration_minutes is not None:
        interruption = minute_text(record.break_duration_minutes)
    else:
        interruption = ZERO_DURATION
    return DayEntry(
        cw=calendar_week_tag(date_text),
        date=date_text,
        special=record.special_day or NORMAL_DAY,
        start=minute_text(record.start_minute),
        end=minute_text(record.end_minute),
        interruption=interruption,
        daily_ot=signed_minute_text(record.daily_overtime_minutes),
        monthly_balance=signed_minute_text(record.running_balance_minutes),
        expected_work_minutes=record.expected_work_minutes,
        revision=record.revision,
    )


def interruption_records(value: str) -> tuple[int | None, tuple[BreakRecord, ...]]:
    token = str(value).strip() or ZERO_DURATION
    if "-" not in token:
        parsed = datetime.strptime(token, "%H:%M")
        return parsed.hour * 60 + parsed.minute, ()
    records = []
    for position, raw in enumerate(token.split(";")):
        start_text, end_text = raw.split("-", 1)
        start = parse_clock(start_text)
        if start is None:
            start = 0
        end = None if end_text == OPEN_END_MARKER else parse_clock(end_text)
        records.append(BreakRecord("", position, start, end))
    return None, tuple(records)
