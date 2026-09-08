from __future__ import annotations

import csv
import os
import tempfile
from pathlib import Path

from znactime.core.models import DayRecord, MonthRecord
from znactime.core.constants import effective_expected_work_minutes
from znactime.core.validation import special_day_text_problem
from znactime.storage.atomic_file import (
    publish_staged_file,
    reject_protected_destination,
)
from znactime.storage.csv_format import (
    CSV_SCHEMA_VERSION,
    CSV_VERSION_MARKER,
    spreadsheet_safe_text,
)
from znactime.storage.errors import ExportError



def _clock(value: int | None) -> str:
    if value is None:
        return "00:00"
    return f"{value // 60:02d}:{value % 60:02d}"


def _signed(value: int) -> str:
    prefix = "-" if value < 0 else ""
    absolute = abs(value)
    return f"{prefix}{absolute // 60:02d}:{absolute % 60:02d}"


def _interruption(day: DayRecord) -> tuple[str, int, bool]:
    if day.breaks:
        value = ";".join(
            f"{_clock(item.start_minute)}-{'...' if item.end_minute is None else _clock(item.end_minute)}"
            for item in day.breaks
        )
        complete = all(item.end_minute is not None for item in day.breaks)
        minutes = sum(
            item.end_minute - item.start_minute
            for item in day.breaks
            if item.end_minute is not None
        )
        return value, minutes, complete
    duration = day.break_duration_minutes or 0
    return _clock(duration), duration, True


def month_rows(month: MonthRecord):
    running = month.opening_balance_minutes
    yield [CSV_VERSION_MARKER, str(CSV_SCHEMA_VERSION)]
    for day in month.days:
        special_day_problem = special_day_text_problem(day.special_day)
        if special_day_problem is not None:
            raise ExportError(
                f"Cannot export {day.work_date.isoformat()}: {special_day_problem}"
            )
        interruption, interruption_minutes, complete = _interruption(day)
        if day.daily_overtime_minutes is not None and day.running_balance_minutes is not None:
            overtime = day.daily_overtime_minutes
            running = day.running_balance_minutes
        elif day.start_minute is not None and day.end_minute is not None and complete:
            overtime = (
                day.end_minute - day.start_minute
                - interruption_minutes - effective_expected_work_minutes(
                    day.special_day, day.expected_work_minutes
                )
            )
            running += overtime
        else:
            overtime = 0
        yield [
            day.work_date.strftime("%d.%m.%Y"),
            spreadsheet_safe_text(day.special_day),
            _clock(day.start_minute),
            _clock(day.end_minute),
            interruption,
            _signed(overtime),
            _signed(running),
        ]


def export_month(
    month: MonthRecord,
    destination: str | Path,
    *,
    overwrite: bool = False,
    protected_paths=(),
) -> None:
    target = Path(destination)
    protected_paths = tuple(protected_paths)
    reject_protected_destination(target, protected_paths)
    if target.exists() and not overwrite:
        raise FileExistsError(str(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    try:
        with os.fdopen(descriptor, "w", newline="", encoding="utf-8") as stream:
            csv.writer(stream).writerows(month_rows(month))
            stream.flush()
            os.fsync(stream.fileno())
        publish_staged_file(
            temporary_name,
            target,
            overwrite=overwrite,
            protected_paths=protected_paths,
        )
    except Exception:
        try:
            Path(temporary_name).unlink()
        except FileNotFoundError:
            pass
        raise
