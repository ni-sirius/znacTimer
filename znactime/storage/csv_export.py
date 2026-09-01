from __future__ import annotations

import csv
import os
import tempfile
from pathlib import Path

from znactime.core.models import DayRecord, MonthRecord
from znactime.storage.atomic_file import (
    publish_staged_file,
    reject_protected_destination,
)


CSV_VERSION_MARKER = "#znacTime-csv"
CSV_SCHEMA_VERSION = 2


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
        interruption, interruption_minutes, complete = _interruption(day)
        if day.daily_overtime_minutes is not None and day.running_balance_minutes is not None:
            overtime = day.daily_overtime_minutes
            running = day.running_balance_minutes
        elif day.start_minute is not None and day.end_minute is not None and complete:
            overtime = (
                day.end_minute - day.start_minute
                - interruption_minutes - day.expected_work_minutes
            )
            running += overtime
        else:
            overtime = 0
        yield [
            day.work_date.strftime("%d.%m.%Y"),
            day.special_day,
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
