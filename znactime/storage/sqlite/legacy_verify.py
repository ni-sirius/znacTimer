from __future__ import annotations

import calendar
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from znactime.storage.legacy_csv_import import LegacyPreflight, preflight_legacy_data


@dataclass(frozen=True)
class VerificationIssue:
    category: str
    location: str
    field: str
    expected: object
    actual: object
    message: str


@dataclass(frozen=True)
class LegacyVerificationReport:
    source_root: Path
    database_path: Path
    preflight: LegacyPreflight
    source_days_checked: int
    database_month_count: int
    database_day_count: int
    database_break_count: int
    database_closed_result_count: int
    local_only_days: int
    errors: tuple[VerificationIssue, ...]
    local_differences: tuple[VerificationIssue, ...]
    derived_differences: tuple[VerificationIssue, ...]

    @property
    def structurally_valid(self) -> bool:
        return not self.errors

    @property
    def exact(self) -> bool:
        return (
            not self.errors
            and not self.local_differences
            and not self.derived_differences
        )

    @property
    def input_difference_days(self) -> int:
        return len(
            {
                issue.location
                for issue in self.local_differences
                if len(issue.location) == 10
            }
        )

    @property
    def derived_difference_days(self) -> int:
        return len({issue.location for issue in self.derived_differences})

    @property
    def exact_input_days(self) -> int:
        return max(0, self.source_days_checked - self.input_difference_days)


def _issue(category, location, field, expected, actual, message):
    return VerificationIssue(category, location, field, expected, actual, message)


def _month_location(year: int, month: int) -> str:
    return f"{year}-{month:02d}"


def _day_location(work_date) -> str:
    return work_date.isoformat()


def _database_counts(db):
    return (
        db.execute("SELECT COUNT(*) FROM months").fetchone()[0],
        db.execute("SELECT COUNT(*) FROM day_entries").fetchone()[0],
        db.execute("SELECT COUNT(*) FROM break_periods").fetchone()[0],
        db.execute("SELECT COUNT(*) FROM closed_day_results").fetchone()[0],
    )


def _verify_import_metadata(db, preflight, errors):
    row = db.execute(
        "SELECT * FROM legacy_imports WHERE source_fingerprint = ?",
        (preflight.source_fingerprint,),
    ).fetchone()
    if row is None:
        errors.append(
            _issue(
                "error",
                "legacy_imports",
                "source_fingerprint",
                preflight.source_fingerprint,
                None,
                "No completed import matches the current byte-for-byte CSV source manifest.",
            )
        )
        return
    expected = {
        "manifest_digest": preflight.manifest_digest,
        "file_count": preflight.file_count,
        "month_count": len(preflight.months),
        "day_count": sum(len(month.days) for month in preflight.months),
        "warning_count": len(preflight.warnings),
    }
    for field, value in expected.items():
        if row[field] != value:
            errors.append(
                _issue(
                    "error",
                    "legacy_imports",
                    field,
                    value,
                    row[field],
                    "Stored import metadata does not match the current source snapshot.",
                )
            )


def _compare_value(differences, location, field, expected, actual):
    if expected == actual:
        return
    differences.append(
        _issue(
            "local",
            location,
            field,
            expected,
            actual,
            "SQLite differs from CSV; the existing/current SQLite value is authoritative.",
        )
    )


def _breaks_for_month(db, month_id):
    result = {}
    for row in db.execute(
        """
        SELECT pause.day_entry_id, pause.position, pause.start_minute, pause.end_minute
        FROM break_periods pause
        JOIN day_entries day ON day.id = pause.day_entry_id
        WHERE day.month_id = ?
        ORDER BY pause.day_entry_id, pause.position
        """,
        (month_id,),
    ).fetchall():
        result.setdefault(row["day_entry_id"], []).append(
            (row["position"], row["start_minute"], row["end_minute"])
        )
    return result


def _open_results(month_row, day_rows, breaks_by_day):
    running = month_row["opening_balance_minutes"]
    results = {}
    for row in day_rows:
        overtime = 0
        if (
            row["start_minute"] is not None
            and row["end_minute"] is not None
            and row["end_minute"] > row["start_minute"]
        ):
            if row["break_duration_minutes"] is None:
                pauses = breaks_by_day.get(row["id"], ())
                if all(end is not None for _position, _start, end in pauses):
                    interruption = sum(
                        end - start for _position, start, end in pauses
                    )
                else:
                    interruption = None
            else:
                interruption = row["break_duration_minutes"]
            if interruption is not None:
                overtime = (
                    row["end_minute"]
                    - row["start_minute"]
                    - interruption
                    - row["expected_work_minutes"]
                )
        running += overtime
        results[row["work_date"]] = (overtime, running)
    return results


def verify_legacy_import(
    source_root: str | Path,
    database_path: str | Path,
) -> LegacyVerificationReport:
    source = Path(source_root).resolve()
    database = Path(database_path).resolve()
    preflight = preflight_legacy_data(source)
    errors: list[VerificationIssue] = []
    local_differences: list[VerificationIssue] = []
    derived_differences: list[VerificationIssue] = []
    for problem in preflight.blocking_errors:
        location = problem.relative_path
        if problem.line is not None:
            location += f":{problem.line}"
        errors.append(
            _issue(
                "error",
                location,
                "source",
                "valid legacy value",
                problem.message,
                "The source cannot be verified until its blocking preflight error is resolved.",
            )
        )

    if not database.is_file():
        errors.append(
            _issue(
                "error",
                str(database),
                "database",
                "existing SQLite file",
                None,
                "The database file does not exist.",
            )
        )
        return LegacyVerificationReport(
            source,
            database,
            preflight,
            0,
            0,
            0,
            0,
            0,
            0,
            tuple(errors),
            (),
            (),
        )

    db = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        # Hold one read snapshot so a running client cannot produce a mixed
        # before/after view while the verifier walks months and days.
        db.execute("PRAGMA query_only = ON")
        db.execute("BEGIN")
        quick_check = db.execute("PRAGMA quick_check").fetchone()[0]
        if quick_check != "ok":
            errors.append(
                _issue(
                    "error",
                    str(database),
                    "integrity",
                    "ok",
                    quick_check,
                    "SQLite quick_check failed.",
                )
            )
        foreign_keys = db.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_keys:
            errors.append(
                _issue(
                    "error",
                    str(database),
                    "foreign_keys",
                    0,
                    len(foreign_keys),
                    "SQLite contains invalid foreign-key relationships.",
                )
            )

        try:
            counts = _database_counts(db)
            _verify_import_metadata(db, preflight, errors)
        except sqlite3.Error as error:
            errors.append(
                _issue(
                    "error",
                    str(database),
                    "schema",
                    "supported znacTime schema",
                    str(error),
                    "The database schema cannot be queried by this verifier.",
                )
            )
            return LegacyVerificationReport(
                source,
                database,
                preflight,
                0,
                0,
                0,
                0,
                0,
                0,
                tuple(errors),
                (),
                (),
            )

        source_days_checked = 0
        local_only_days = 0
        for source_month in preflight.months:
            month_location = _month_location(source_month.year, source_month.month)
            month_row = db.execute(
                """
                SELECT * FROM months
                WHERE year = ? AND month = ?
                ORDER BY dataset_id LIMIT 1
                """,
                (source_month.year, source_month.month),
            ).fetchone()
            if month_row is None:
                errors.append(
                    _issue(
                        "error",
                        month_location,
                        "month",
                        "present",
                        "missing",
                        "A source month is missing from SQLite.",
                    )
                )
                continue

            _compare_value(
                local_differences,
                month_location,
                "status",
                "closed" if source_month.closed else "open",
                month_row["status"],
            )
            source_opening = (
                source_month.days[0].running_balance_minutes
                - source_month.days[0].daily_overtime_minutes
                if source_month.days
                else 0
            )
            _compare_value(
                local_differences,
                month_location,
                "opening_balance_minutes",
                source_opening,
                month_row["opening_balance_minutes"],
            )
            if source_month.closed and source_month.days:
                _compare_value(
                    local_differences,
                    month_location,
                    "closing_balance_minutes",
                    source_month.days[-1].running_balance_minutes,
                    month_row["closing_balance_minutes"],
                )

            day_rows = db.execute(
                "SELECT * FROM day_entries WHERE month_id = ? ORDER BY work_date",
                (month_row["id"],),
            ).fetchall()
            expected_calendar_days = calendar.monthrange(
                source_month.year, source_month.month
            )[1]
            if len(day_rows) != expected_calendar_days:
                errors.append(
                    _issue(
                        "error",
                        month_location,
                        "calendar_day_count",
                        expected_calendar_days,
                        len(day_rows),
                        "SQLite must contain exactly one row for every calendar day.",
                    )
                )
            rows_by_date = {row["work_date"]: row for row in day_rows}
            source_dates = {day.work_date.isoformat() for day in source_month.days}
            local_only_days += sum(
                row["work_date"] not in source_dates for row in day_rows
            )
            breaks_by_day = _breaks_for_month(db, month_row["id"])
            closed_results = {
                row["day_entry_id"]: row
                for row in db.execute(
                    """
                    SELECT result.* FROM closed_day_results result
                    JOIN day_entries day ON day.id = result.day_entry_id
                    WHERE day.month_id = ?
                    """,
                    (month_row["id"],),
                ).fetchall()
            }
            should_have_results = month_row["status"] == "closed"
            for day_row in day_rows:
                has_result = day_row["id"] in closed_results
                if has_result == should_have_results:
                    continue
                errors.append(
                    _issue(
                        "error",
                        day_row["work_date"],
                        "closed_day_result",
                        "present" if should_have_results else "absent",
                        "present" if has_result else "missing",
                        "Closed-result presence does not match the SQLite month state.",
                    )
                )
            open_results = (
                _open_results(month_row, day_rows, breaks_by_day)
                if month_row["status"] == "open"
                else {}
            )

            for source_day in source_month.days:
                source_days_checked += 1
                location = _day_location(source_day.work_date)
                day_row = rows_by_date.get(source_day.work_date.isoformat())
                if day_row is None:
                    errors.append(
                        _issue(
                            "error",
                            location,
                            "day",
                            "present",
                            "missing",
                            "A source day is missing from SQLite.",
                        )
                    )
                    continue
                _compare_value(
                    local_differences,
                    location,
                    "special_day",
                    source_day.special_day,
                    day_row["special_day"],
                )
                _compare_value(
                    local_differences,
                    location,
                    "start_minute",
                    source_day.start_minute,
                    day_row["start_minute"],
                )
                _compare_value(
                    local_differences,
                    location,
                    "end_minute",
                    source_day.end_minute,
                    day_row["end_minute"],
                )
                _compare_value(
                    local_differences,
                    location,
                    "break_duration_minutes",
                    source_day.break_duration_minutes,
                    day_row["break_duration_minutes"],
                )
                expected_breaks = tuple(
                    (position, pause.start_minute, pause.end_minute)
                    for position, pause in enumerate(source_day.breaks)
                )
                actual_breaks = tuple(breaks_by_day.get(day_row["id"], ()))
                _compare_value(
                    local_differences,
                    location,
                    "break_periods",
                    expected_breaks,
                    actual_breaks,
                )

                if month_row["status"] == "closed":
                    result = closed_results.get(day_row["id"])
                    if result is not None:
                        _compare_value(
                            local_differences,
                            location,
                            "daily_overtime_minutes",
                            source_day.daily_overtime_minutes,
                            result["daily_overtime_minutes"],
                        )
                        _compare_value(
                            local_differences,
                            location,
                            "running_balance_minutes",
                            source_day.running_balance_minutes,
                            result["running_balance_minutes"],
                        )
                else:
                    calculated = open_results.get(source_day.work_date.isoformat())
                    if calculated is not None:
                        for field, expected, actual in (
                            (
                                "derived_daily_overtime_minutes",
                                source_day.daily_overtime_minutes,
                                calculated[0],
                            ),
                            (
                                "derived_running_balance_minutes",
                                source_day.running_balance_minutes,
                                calculated[1],
                            ),
                        ):
                            if expected != actual:
                                derived_differences.append(
                                    _issue(
                                        "derived",
                                        location,
                                        field,
                                        expected,
                                        actual,
                                        "The open-month result is derived and changed because SQLite input is authoritative.",
                                    )
                                )

        return LegacyVerificationReport(
            source,
            database,
            preflight,
            source_days_checked,
            counts[0],
            counts[1],
            counts[2],
            counts[3],
            local_only_days,
            tuple(errors),
            tuple(local_differences),
            tuple(derived_differences),
        )
    finally:
        db.close()
