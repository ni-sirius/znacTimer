from __future__ import annotations

import calendar
import csv
import hashlib
import os
import re
import stat
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from znactime.core.constants import NORMAL_DAY
from znactime.core.validation import special_day_text_problem
from znactime.storage.csv_format import (
    CSV_SCHEMA_VERSION,
    CSV_VERSION_MARKER,
    decode_spreadsheet_safe_text,
)
from znactime.storage.errors import StorageValidationError


_MONTH_FILE = re.compile(r"^(?P<year>\d{4})_tmp_(?P<month>\d{2})\.csv$")
_CLOSED_FLAG = re.compile(r"^closed_(?P<month>\d{2})\.flag$")
_TIME = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
_SIGNED_DURATION = re.compile(r"^-?\d+:[0-5]\d$")

MAX_RECOGNIZED_FILES = 2_400
MAX_CSV_BYTES = 1 * 1024 * 1024
MAX_FLAG_BYTES = 64 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_CSV_ROWS = 400
MAX_CSV_ROW_BYTES = 64 * 1024
_HASH_CHUNK_BYTES = 64 * 1024

ProgressCallback = Callable[[str, int, int], None]
CancellationCallback = Callable[[], bool]


class LegacyImportCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class ImportIssue:
    severity: str
    relative_path: str
    line: int | None
    message: str


@dataclass(frozen=True)
class LegacyBreak:
    start_minute: int
    end_minute: int | None


@dataclass(frozen=True)
class LegacyDay:
    work_date: date
    special_day: str
    start_minute: int | None
    end_minute: int | None
    break_duration_minutes: int | None
    breaks: tuple[LegacyBreak, ...]
    daily_overtime_minutes: int
    running_balance_minutes: int


@dataclass(frozen=True)
class LegacyMonth:
    year: int
    month: int
    closed: bool
    schema_version: int | None
    days: tuple[LegacyDay, ...]


@dataclass(frozen=True)
class LegacyPreflight:
    source_root: Path
    source_fingerprint: str
    manifest_digest: str
    file_count: int
    ignored_file_count: int
    months: tuple[LegacyMonth, ...]
    issues: tuple[ImportIssue, ...]
    encodings: tuple[str, ...]

    @property
    def blocking_errors(self) -> tuple[ImportIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "error")

    @property
    def warnings(self) -> tuple[ImportIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "warning")


@dataclass(frozen=True)
class LegacyNormalization:
    """One intentional source-to-database change made by strict import."""

    location: str
    field: str
    source_value: object
    imported_value: object
    reason: str


@dataclass(frozen=True)
class LegacyMergeResult:
    """Outcome of merging one immutable legacy source snapshot into SQLite."""

    source_root: Path
    already_imported: bool
    months_created: int
    months_merged: int
    months_closed: int
    closures_kept_open: int
    days_imported: int
    days_kept_current: int
    days_unchanged: int
    warning_count: int
    normalizations: tuple[LegacyNormalization, ...] = ()
    log_path: Path | None = None


@dataclass(frozen=True)
class _RecognizedFile:
    path: Path
    relative_path: str
    size: int
    signature: tuple[int, int, int, int]


def _cancel_if_requested(cancelled: CancellationCallback | None) -> None:
    if cancelled is not None and cancelled():
        raise LegacyImportCancelled("Legacy import was cancelled.")


def _report_progress(
    progress: ProgressCallback | None,
    phase: str,
    completed: int,
    total: int,
) -> None:
    if progress is not None:
        progress(phase, completed, total)


def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction and is_junction())


def _signature(file_stat) -> tuple[int, int, int, int]:
    return (
        file_stat.st_dev,
        file_stat.st_ino,
        file_stat.st_size,
        file_stat.st_mtime_ns,
    )


def _discover_legacy_files(
    root: Path,
    *,
    cancelled: CancellationCallback | None,
) -> tuple[tuple[_RecognizedFile, ...], int]:
    discovered: list[_RecognizedFile] = []
    ignored = 0
    total_bytes = 0
    for year_dir in sorted(root.iterdir(), key=lambda item: item.name):
        _cancel_if_requested(cancelled)
        if not re.fullmatch(r"\d{4}", year_dir.name):
            ignored += 1
            continue
        if _is_link_or_junction(year_dir):
            raise ValueError(f"Legacy import does not allow links: {year_dir.name}")
        if not year_dir.is_dir():
            ignored += 1
            continue
        for path in sorted(year_dir.iterdir(), key=lambda item: item.name):
            _cancel_if_requested(cancelled)
            is_month = _MONTH_FILE.fullmatch(path.name) is not None
            is_flag = _CLOSED_FLAG.fullmatch(path.name) is not None
            if not is_month and not is_flag:
                ignored += 1
                continue
            relative = path.relative_to(root).as_posix()
            if _is_link_or_junction(path):
                raise ValueError(f"Legacy import does not allow links: {relative}")
            file_stat = path.lstat()
            if not stat.S_ISREG(file_stat.st_mode):
                raise ValueError(f"Legacy import expects a regular file: {relative}")
            if is_month and file_stat.st_size > MAX_CSV_BYTES:
                raise ValueError(
                    f"Legacy CSV exceeds the {MAX_CSV_BYTES}-byte limit: {relative}"
                )
            if is_flag and file_stat.st_size > MAX_FLAG_BYTES:
                raise ValueError(
                    f"Closed flag exceeds the {MAX_FLAG_BYTES}-byte limit: {relative}"
                )
            total_bytes += file_stat.st_size
            if total_bytes > MAX_TOTAL_BYTES:
                raise ValueError(
                    f"Legacy source exceeds the {MAX_TOTAL_BYTES}-byte total limit."
                )
            discovered.append(
                _RecognizedFile(
                    path,
                    relative,
                    file_stat.st_size,
                    _signature(file_stat),
                )
            )
            if len(discovered) > MAX_RECOGNIZED_FILES:
                raise ValueError(
                    "Legacy source exceeds the "
                    f"{MAX_RECOGNIZED_FILES}-file limit."
                )
    return tuple(discovered), ignored


def _assert_source_unchanged(source: _RecognizedFile) -> None:
    if _is_link_or_junction(source.path):
        raise ValueError(
            f"Legacy source became a link while reading: {source.relative_path}"
        )
    if _signature(source.path.lstat()) != source.signature:
        raise ValueError(
            f"Legacy source changed while it was being read: {source.relative_path}"
        )


def _hash_source_file(
    source: _RecognizedFile,
    *,
    cancelled: CancellationCallback | None,
) -> str:
    digest = hashlib.sha256()
    with source.path.open("rb") as stream:
        opened = stream.fileno()
        if _signature(os.fstat(opened)) != source.signature:
            raise ValueError(
                f"Legacy source changed before it was read: {source.relative_path}"
            )
        while True:
            _cancel_if_requested(cancelled)
            chunk = stream.read(_HASH_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    _assert_source_unchanged(source)
    return digest.hexdigest()


def _read_csv_rows(
    source: _RecognizedFile,
    encoding: str,
    *,
    cancelled: CancellationCallback | None,
) -> list[list[str]]:
    rows: list[list[str]] = []
    with source.path.open("r", newline="", encoding=encoding) as stream:
        if _signature(os.fstat(stream.fileno())) != source.signature:
            raise ValueError(
                f"Legacy source changed before it was parsed: {source.relative_path}"
            )
        for row in csv.reader(stream, strict=True):
            _cancel_if_requested(cancelled)
            if len(rows) >= MAX_CSV_ROWS:
                raise ValueError(
                    f"Legacy CSV exceeds the {MAX_CSV_ROWS}-row limit: "
                    f"{source.relative_path}"
                )
            row_bytes = sum(
                len(field.encode("utf-8")) for field in row
            ) + max(0, len(row) - 1)
            if row_bytes > MAX_CSV_ROW_BYTES:
                raise ValueError(
                    f"Legacy CSV row exceeds the {MAX_CSV_ROW_BYTES}-byte limit: "
                    f"{source.relative_path}:{len(rows) + 1}"
                )
            rows.append(row)
    _assert_source_unchanged(source)
    return rows


def _minutes(value: str) -> int:
    hours, minutes = value.split(":", 1)
    return int(hours) * 60 + int(minutes)


def _signed_minutes(value: str) -> int:
    negative = value.startswith("-")
    raw = value[1:] if negative else value
    result = _minutes(raw)
    return -result if negative else result


def _clock(
    value: str,
    *,
    relative_path: str,
    line: int,
    field: str,
    issues: list[ImportIssue],
) -> int | None:
    token = value.strip()
    if token in ("", "00:00"):
        if token == "00:00":
            issues.append(
                ImportIssue(
                    "warning", relative_path, line,
                    f"Legacy {field} 00:00 is interpreted as unset, not midnight.",
                )
            )
        return None
    if not _TIME.fullmatch(token):
        issues.append(ImportIssue("error", relative_path, line, f"Invalid {field} time."))
        return None
    return _minutes(token)


def _result(
    value: str,
    *,
    relative_path: str,
    line: int,
    field: str,
    issues: list[ImportIssue],
) -> int:
    token = value.strip()
    if token == "":
        issues.append(ImportIssue("warning", relative_path, line, f"Empty {field} treated as zero."))
        return 0
    if not _SIGNED_DURATION.fullmatch(token):
        issues.append(ImportIssue("error", relative_path, line, f"Invalid {field}."))
        return 0
    return _signed_minutes(token)


def _interruption(
    value: str,
    *,
    relative_path: str,
    line: int,
    issues: list[ImportIssue],
) -> tuple[int | None, tuple[LegacyBreak, ...]]:
    token = value.strip()
    if token in ("", "00:00"):
        return 0, ()
    if "-" not in token:
        if not _TIME.fullmatch(token):
            issues.append(ImportIssue("error", relative_path, line, "Invalid interruption duration."))
            return 0, ()
        return _minutes(token), ()

    periods: list[LegacyBreak] = []
    open_count = 0
    for raw_period in token.split(";"):
        parts = raw_period.strip().split("-")
        if len(parts) != 2 or not _TIME.fullmatch(parts[0].strip()):
            issues.append(ImportIssue("error", relative_path, line, "Invalid interruption period."))
            return None, ()
        start = _minutes(parts[0].strip())
        end_text = parts[1].strip()
        if end_text == "...":
            end = None
            open_count += 1
        elif _TIME.fullmatch(end_text):
            end = _minutes(end_text)
            if end <= start:
                issues.append(ImportIssue("error", relative_path, line, "Reversed interruption period."))
        else:
            issues.append(ImportIssue("error", relative_path, line, "Invalid interruption end."))
            return None, ()
        periods.append(LegacyBreak(start, end))
    if open_count > 1:
        issues.append(ImportIssue("error", relative_path, line, "Multiple active pauses."))
    ordered = sorted(periods, key=lambda item: item.start_minute)
    for previous, current in zip(ordered, ordered[1:]):
        if previous.end_minute is None or previous.end_minute > current.start_minute:
            issues.append(ImportIssue("error", relative_path, line, "Overlapping interruption periods."))
    return None, tuple(ordered)


def _parse_month(
    source: _RecognizedFile,
    root: Path,
    issues: list[ImportIssue],
    *,
    closed: bool,
    cancelled: CancellationCallback | None,
) -> tuple[LegacyMonth | None, str]:
    path = source.path
    match = _MONTH_FILE.match(path.name)
    if match is None:
        raise StorageValidationError(
            "A recognized monthly CSV no longer matches its validated file name."
        )
    year = int(match.group("year"))
    month = int(match.group("month"))
    relative = path.relative_to(root).as_posix()
    if not 1 <= year <= 9999 or not 1 <= month <= 12:
        issues.append(ImportIssue("error", relative, None, "Invalid year or month in file name."))
        return None, "unknown"
    if path.parent.name != str(year):
        issues.append(
            ImportIssue(
                "error",
                relative,
                None,
                "Monthly CSV is not inside its matching year directory.",
            )
        )
    try:
        rows = _read_csv_rows(source, "utf-8-sig", cancelled=cancelled)
        encoding = "utf-8-sig"
    except UnicodeDecodeError:
        try:
            rows = _read_csv_rows(source, "cp1252", cancelled=cancelled)
            encoding = "cp1252"
        except UnicodeError:
            issues.append(ImportIssue("error", relative, None, "File is not valid UTF-8 or Windows-1252."))
            return None, "unknown"
    if encoding != "utf-8-sig":
        issues.append(ImportIssue("warning", relative, None, f"Decoded as {encoding}."))
    schema_version = None
    first_line = 1
    if rows and rows[0][:1] == [CSV_VERSION_MARKER]:
        try:
            schema_version = int(rows[0][1])
        except (IndexError, ValueError):
            issues.append(ImportIssue("error", relative, 1, "Invalid CSV version marker."))
        if schema_version not in (1, 2, CSV_SCHEMA_VERSION):
            issues.append(ImportIssue("error", relative, 1, "Unsupported CSV schema version."))
        rows = rows[1:]
        first_line = 2

    parsed: dict[date, LegacyDay] = {}
    for offset, raw_row in enumerate(rows):
        line = first_line + offset
        row = list(raw_row)
        if row and row[0].startswith("CW-"):
            row = row[1:]
        if len(row) < 7:
            issues.append(ImportIssue("error", relative, line, "CSV row has fewer than seven fields."))
            continue
        if len(row) > 7:
            issues.append(ImportIssue("warning", relative, line, "Extra CSV fields are ignored."))
        try:
            work_date = datetime.strptime(row[0].strip(), "%d.%m.%Y").date()
        except ValueError:
            issues.append(ImportIssue("error", relative, line, "Invalid work date."))
            continue
        if (work_date.year, work_date.month) != (year, month):
            issues.append(ImportIssue("error", relative, line, "Work date does not belong to its file month."))
        if work_date in parsed:
            issues.append(ImportIssue("error", relative, line, "Duplicate work date."))
            continue
        start = _clock(row[2], relative_path=relative, line=line, field="start", issues=issues)
        end = _clock(row[3], relative_path=relative, line=line, field="end", issues=issues)
        duration, periods = _interruption(row[4], relative_path=relative, line=line, issues=issues)
        daily = _result(row[5], relative_path=relative, line=line, field="daily overtime", issues=issues)
        running = _result(row[6], relative_path=relative, line=line, field="running balance", issues=issues)
        decoded_special_day = decode_spreadsheet_safe_text(row[1], schema_version)
        special_day_problem = (
            special_day_text_problem(decoded_special_day)
            if decoded_special_day
            else None
        )
        special_day = decoded_special_day.strip() or NORMAL_DAY
        if special_day_problem is not None:
            issues.append(
                ImportIssue("error", relative, line, special_day_problem)
            )
        parsed[work_date] = LegacyDay(
            work_date=work_date,
            special_day=special_day,
            start_minute=start,
            end_minute=end,
            break_duration_minutes=duration,
            breaks=periods,
            daily_overtime_minutes=daily,
            running_balance_minutes=running,
        )

    expected_dates = {
        date(year, month, day_number)
        for day_number in range(1, calendar.monthrange(year, month)[1] + 1)
    }
    missing = sorted(expected_dates - set(parsed))
    if missing:
        issues.append(
            ImportIssue(
                "warning", relative, None,
                f"Month is missing {len(missing)} calendar day row(s); blank rows will be created.",
            )
        )
    for day in parsed.values():
        if (day.start_minute is None) != (day.end_minute is None):
            issues.append(
                ImportIssue(
                    "warning", relative, None,
                    f"Day {day.work_date} has one missing clock time; its work interval "
                    "and interruptions will be cleared during import.",
                )
            )
            continue
        if day.start_minute is not None and day.end_minute <= day.start_minute:
            issues.append(
                ImportIssue(
                    "warning", relative, None,
                    f"Day {day.work_date} has a reversed workday; its work interval "
                    "and interruptions will be cleared during import.",
                )
            )
            continue
        if day.start_minute is None:
            if day.break_duration_minutes not in (None, 0) or day.breaks:
                issues.append(
                    ImportIssue(
                        "warning", relative, None,
                        f"Day {day.work_date} has interruptions without a work interval; "
                        "they will be cleared during import.",
                    )
                )
            continue
        elapsed = day.end_minute - day.start_minute
        if day.break_duration_minutes is not None:
            interruption = day.break_duration_minutes
            if interruption > elapsed:
                issues.append(
                    ImportIssue(
                        "warning", relative, None,
                        f"Day {day.work_date} has a break duration longer than its work "
                        "interval; the break will be cleared during import.",
                    )
                )
                interruption = 0
        else:
            invalid_breaks = any(
                item.end_minute is None
                or item.start_minute < day.start_minute
                or item.end_minute > day.end_minute
                for item in day.breaks
            )
            if invalid_breaks:
                issues.append(
                    ImportIssue(
                        "warning", relative, None,
                        f"Day {day.work_date} has an active or out-of-range pause; all "
                        "pauses for that day will be cleared during import.",
                    )
                )
                interruption = 0
            else:
                interruption = sum(
                    item.end_minute - item.start_minute for item in day.breaks
                )
        inferred = elapsed - interruption - day.daily_overtime_minutes
        if not 0 <= inferred <= 1440:
            issues.append(
                ImportIssue(
                    "warning", relative, None,
                    f"Day {day.work_date} work limit cannot be inferred; the active "
                    "schedule will be used and derived results will be recalculated.",
                )
            )
    return LegacyMonth(year, month, closed, schema_version, tuple(parsed[key] for key in sorted(parsed))), encoding


def preflight_legacy_data(
    source_root: str | Path,
    *,
    progress: ProgressCallback | None = None,
    cancelled: CancellationCallback | None = None,
) -> LegacyPreflight:
    requested_root = Path(source_root)
    if _is_link_or_junction(requested_root):
        raise ValueError("Legacy data root cannot be a symlink or junction.")
    root = requested_root.resolve()
    if not root.is_dir():
        raise ValueError("Legacy data root does not exist or is not a directory.")
    _report_progress(progress, "Discovering legacy files", 0, 0)
    files, ignored_file_count = _discover_legacy_files(root, cancelled=cancelled)
    manifest = []
    for index, source in enumerate(files, 1):
        digest = _hash_source_file(source, cancelled=cancelled)
        manifest.append(
            f"{source.relative_path}\0{source.size}\0{digest}"
        )
        _report_progress(progress, "Hashing legacy files", index, len(files))
    manifest_text = "\n".join(manifest)
    manifest_digest = hashlib.sha256(manifest_text.encode("utf-8")).hexdigest()
    source_fingerprint = hashlib.sha256(
        ("znactime-legacy-v1\0" + manifest_digest).encode("utf-8")
    ).hexdigest()

    issues: list[ImportIssue] = []
    months: list[LegacyMonth] = []
    month_sources: dict[tuple[int, int], str] = {}
    encodings: set[str] = set()
    closed_months = {
        (int(source.path.parent.name), int(_CLOSED_FLAG.fullmatch(source.path.name).group("month")))
        for source in files
        if _CLOSED_FLAG.fullmatch(source.path.name)
    }
    month_files = [source for source in files if _MONTH_FILE.fullmatch(source.path.name)]
    for index, source in enumerate(month_files, 1):
        match = _MONTH_FILE.fullmatch(source.path.name)
        if match is None:
            raise StorageValidationError(
                "A recognized monthly CSV no longer matches its validated file name."
            )
        key = (int(match.group("year")), int(match.group("month")))
        try:
            parsed, encoding = _parse_month(
                source,
                root,
                issues,
                closed=key in closed_months,
                cancelled=cancelled,
            )
        except csv.Error as error:
            issues.append(
                ImportIssue(
                    "error",
                    source.relative_path,
                    None,
                    f"Malformed CSV: {error}.",
                )
            )
            parsed, encoding = None, "unknown"
        _report_progress(progress, "Parsing legacy months", index, len(month_files))
        if parsed is not None:
            encodings.add(encoding)
            parsed_key = (parsed.year, parsed.month)
            if parsed_key in month_sources:
                issues.append(
                    ImportIssue(
                        "error",
                        source.relative_path,
                        None,
                        f"Duplicate logical month; already provided by {month_sources[parsed_key]}.",
                    )
                )
            else:
                month_sources[parsed_key] = source.relative_path
                months.append(parsed)
    for source in files:
        path = source.path
        flag = _CLOSED_FLAG.fullmatch(path.name)
        if flag is None:
            continue
        relative = path.relative_to(root).as_posix()
        try:
            year = int(path.parent.name)
            month = int(flag.group("month"))
        except ValueError:
            issues.append(
                ImportIssue("error", relative, None, "Closed flag is not inside a year directory.")
            )
            continue
        if not 1 <= year <= 9999 or not 1 <= month <= 12:
            issues.append(ImportIssue("error", relative, None, "Invalid closed-month flag."))
        elif (year, month) not in month_sources:
            issues.append(
                ImportIssue("error", relative, None, "Closed-month flag has no matching monthly CSV.")
            )
    if not months:
        issues.append(ImportIssue("error", ".", None, "No recognized legacy monthly CSV files found."))
    months.sort(key=lambda item: (item.year, item.month))
    open_seen: LegacyMonth | None = None
    for item in months:
        if not item.closed and open_seen is None:
            open_seen = item
        elif item.closed and open_seen is not None:
            issues.append(
                ImportIssue(
                    "warning", f"{item.year}/{item.month:02}", None,
                    "Closed month follows an earlier existing open month; it will remain "
                    "open so the database retains a closable chronological chain.",
                )
            )
    for previous, current in zip(months, months[1:]):
        if not current.days:
            continue
        current_opening = (
            current.days[0].running_balance_minutes
            - current.days[0].daily_overtime_minutes
        )
        is_immediate = (
            previous.year * 12 + previous.month + 1
            == current.year * 12 + current.month
        )
        expected_opening = (
            previous.days[-1].running_balance_minutes
            if is_immediate and previous.closed and previous.days
            else 0
        )
        if current_opening != expected_opening:
            issues.append(
                ImportIssue(
                    "error", f"{current.year}/{current.month:02}", None,
                    "Opening balance does not match the preceding closed-month chain.",
                )
            )
    return LegacyPreflight(
        source_root=root,
        source_fingerprint=source_fingerprint,
        manifest_digest=manifest_digest,
        file_count=len(files),
        ignored_file_count=ignored_file_count,
        months=tuple(months),
        issues=tuple(issues),
        encodings=tuple(sorted(encodings)),
    )
