from __future__ import annotations

import calendar
import csv
import hashlib
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from znactime.core.constants import NORMAL_DAY


_MONTH_FILE = re.compile(r"^(?P<year>\d{4})_tmp_(?P<month>\d{2})\.csv$")
_CLOSED_FLAG = re.compile(r"^closed_(?P<month>\d{2})\.flag$")
_TIME = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
_SIGNED_DURATION = re.compile(r"^-?\d+:[0-5]\d$")
_VERSION_MARKER = "#znacTime-csv"


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


def _minutes(value: str) -> int:
    hours, minutes = value.split(":", 1)
    return int(hours) * 60 + int(minutes)


def _signed_minutes(value: str) -> int:
    negative = value.startswith("-")
    raw = value[1:] if negative else value
    result = _minutes(raw)
    return -result if negative else result


def _decode(raw: bytes) -> tuple[str, str]:
    try:
        return raw.decode("utf-8-sig"), "utf-8-sig"
    except UnicodeDecodeError:
        return raw.decode("cp1252"), "cp1252"


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
    path: Path,
    root: Path,
    issues: list[ImportIssue],
) -> tuple[LegacyMonth | None, str]:
    match = _MONTH_FILE.match(path.name)
    assert match is not None
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
        text, encoding = _decode(path.read_bytes())
    except UnicodeError:
        issues.append(ImportIssue("error", relative, None, "File is not valid UTF-8 or Windows-1252."))
        return None, "unknown"
    if encoding != "utf-8-sig":
        issues.append(ImportIssue("warning", relative, None, f"Decoded as {encoding}."))
    try:
        rows = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except csv.Error as error:
        issues.append(ImportIssue("error", relative, None, f"Malformed CSV: {error}."))
        return None, encoding
    schema_version = None
    first_line = 1
    if rows and rows[0][:1] == [_VERSION_MARKER]:
        try:
            schema_version = int(rows[0][1])
        except (IndexError, ValueError):
            issues.append(ImportIssue("error", relative, 1, "Invalid CSV version marker."))
        if schema_version not in (1, 2):
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
        parsed[work_date] = LegacyDay(
            work_date=work_date,
            special_day=row[1].strip() or NORMAL_DAY,
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
    closed = (path.parent / f"closed_{month:02}.flag").exists()
    if closed:
        for day in parsed.values():
            if (day.start_minute is None) != (day.end_minute is None):
                issues.append(
                    ImportIssue("warning", relative, None, f"Closed day {day.work_date} has one missing clock time; the historical row and results will be preserved.")
                )
                continue
            if day.start_minute is not None and day.end_minute <= day.start_minute:
                issues.append(
                    ImportIssue("warning", relative, None, f"Closed day {day.work_date} has a reversed workday; the historical row and results will be preserved.")
                )
                continue
            if day.start_minute is not None:
                if day.break_duration_minutes is not None:
                    interruption = day.break_duration_minutes
                else:
                    if any(item.end_minute is None for item in day.breaks):
                        issues.append(
                            ImportIssue("warning", relative, None, f"Closed day {day.work_date} has an active pause; the historical row and results will be preserved.")
                        )
                        continue
                    if any(
                        item.start_minute < day.start_minute or item.end_minute > day.end_minute
                        for item in day.breaks
                    ):
                        issues.append(
                            ImportIssue("warning", relative, None, f"Closed day {day.work_date} has a pause outside the workday; the historical row and results will be preserved.")
                        )
                    interruption = sum(item.end_minute - item.start_minute for item in day.breaks)
                inferred = day.end_minute - day.start_minute - interruption - day.daily_overtime_minutes
                if not 0 <= inferred <= 1440:
                    issues.append(
                        ImportIssue(
                            "warning", relative, None,
                            f"Closed day {day.work_date} work limit cannot be inferred; migration default will be used.",
                        )
                    )
    return LegacyMonth(year, month, closed, schema_version, tuple(parsed[key] for key in sorted(parsed))), encoding


def preflight_legacy_data(source_root: str | Path) -> LegacyPreflight:
    root = Path(source_root).resolve()
    if not root.is_dir():
        raise ValueError("Legacy data root does not exist or is not a directory.")
    files = sorted((path for path in root.rglob("*") if path.is_file()), key=lambda p: p.relative_to(root).as_posix())
    manifest = []
    for path in files:
        raw = path.read_bytes()
        manifest.append(
            f"{path.relative_to(root).as_posix()}\0{len(raw)}\0{hashlib.sha256(raw).hexdigest()}"
        )
    manifest_text = "\n".join(manifest)
    manifest_digest = hashlib.sha256(manifest_text.encode("utf-8")).hexdigest()
    source_fingerprint = hashlib.sha256(
        ("znactime-legacy-v1\0" + manifest_digest).encode("utf-8")
    ).hexdigest()

    issues: list[ImportIssue] = []
    months: list[LegacyMonth] = []
    month_sources: dict[tuple[int, int], str] = {}
    encodings: set[str] = set()
    for path in files:
        if _MONTH_FILE.match(path.name):
            parsed, encoding = _parse_month(path, root, issues)
            encodings.add(encoding)
            if parsed:
                key = (parsed.year, parsed.month)
                relative = path.relative_to(root).as_posix()
                if key in month_sources:
                    issues.append(
                        ImportIssue(
                            "error",
                            relative,
                            None,
                            f"Duplicate logical month; already provided by {month_sources[key]}.",
                        )
                    )
                else:
                    month_sources[key] = relative
                    months.append(parsed)
    for path in files:
        flag = _CLOSED_FLAG.match(path.name)
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
                    "Closed month follows an earlier existing open month; independent legacy closure states will be preserved.",
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
        months=tuple(months),
        issues=tuple(issues),
        encodings=tuple(sorted(encodings)),
    )
