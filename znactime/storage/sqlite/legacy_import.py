from __future__ import annotations

import calendar
import sqlite3
import uuid
from datetime import date
from pathlib import Path

from znactime.config import VERSION
from znactime.core.constants import NORMAL_DAY
from znactime.storage.errors import StorageValidationError
from znactime.storage.legacy_csv_import import (
    LegacyDay,
    LegacyMergeResult,
    LegacyMonth,
    LegacyPreflight,
)
from znactime.storage.sqlite.connection import transaction, translate_error
from znactime.storage.sqlite.repository import SQLiteRepository, _utc_text


def _inferred_expected(day: LegacyDay, fallback: int) -> int:
    if day.start_minute is None or day.end_minute is None:
        return fallback
    if day.break_duration_minutes is not None:
        interruption = day.break_duration_minutes
    elif all(item.end_minute is not None for item in day.breaks):
        interruption = sum(item.end_minute - item.start_minute for item in day.breaks)
    else:
        return fallback
    inferred = day.end_minute - day.start_minute - interruption - day.daily_overtime_minutes
    return inferred if 0 <= inferred <= 1440 else fallback


def _legacy_day_has_data(day: LegacyDay, *, include_results: bool) -> bool:
    return bool(
        day.special_day != NORMAL_DAY
        or day.start_minute is not None
        or day.end_minute is not None
        or day.break_duration_minutes not in (None, 0)
        or day.breaks
        or (
            include_results
            and (day.daily_overtime_minutes or day.running_balance_minutes)
        )
    )


def _local_day_has_data(db, day_row) -> bool:
    """Generated revision-1 placeholders are importable; local state is not."""
    if (
        day_row["revision"] > 1
        or day_row["special_day"] != NORMAL_DAY
        or day_row["start_minute"] is not None
        or day_row["end_minute"] is not None
        or day_row["break_duration_minutes"] not in (None, 0)
        or day_row["expected_minutes_overridden"]
    ):
        return True
    if db.execute(
        "SELECT 1 FROM break_periods WHERE day_entry_id = ?", (day_row["id"],)
    ).fetchone():
        return True
    return bool(
        db.execute(
            "SELECT 1 FROM active_workday WHERE day_entry_id = ?", (day_row["id"],)
        ).fetchone()
    )


def _ensure_month(repository: SQLiteRepository, db, year: int, month: int, now: str):
    dataset_id = repository._dataset_id(db)
    existing = db.execute(
        "SELECT * FROM months WHERE dataset_id = ? AND year = ? AND month = ?",
        (dataset_id, year, month),
    ).fetchone()
    if existing is not None:
        return existing, False

    previous_year, previous_month = (year, month - 1) if month > 1 else (year - 1, 12)
    previous = db.execute(
        """
        SELECT closing_balance_minutes FROM months
        WHERE dataset_id = ? AND year = ? AND month = ? AND status = 'closed'
        """,
        (dataset_id, previous_year, previous_month),
    ).fetchone()
    opening = previous[0] if previous else 0
    month_id = db.execute(
        """
        INSERT INTO months(
            dataset_id, year, month, status, opening_balance_minutes,
            created_at, updated_at
        ) VALUES (?, ?, ?, 'open', ?, ?, ?)
        """,
        (dataset_id, year, month, opening, now, now),
    ).lastrowid
    for day_number in range(1, calendar.monthrange(year, month)[1] + 1):
        work_date = date(year, month, day_number)
        db.execute(
            """
            INSERT INTO day_entries(
                month_id, work_date, special_day, start_minute, end_minute,
                break_duration_minutes, expected_work_minutes,
                expected_minutes_overridden, created_at, updated_at
            ) VALUES (?, ?, ?, NULL, NULL, 0, ?, 0, ?, ?)
            """,
            (
                month_id,
                work_date.isoformat(),
                NORMAL_DAY,
                repository._expected_minutes(work_date, db),
                now,
                now,
            ),
        )
    return db.execute("SELECT * FROM months WHERE id = ?", (month_id,)).fetchone(), True


def _apply_legacy_day(db, day_row, legacy_day: LegacyDay, now: str, expected: int):
    db.execute("DELETE FROM break_periods WHERE day_entry_id = ?", (day_row["id"],))
    db.execute(
        """
        UPDATE day_entries SET special_day = ?, start_minute = ?, end_minute = ?,
            break_duration_minutes = ?, expected_work_minutes = ?,
            expected_minutes_overridden = 0, updated_at = ?, revision = revision + 1
        WHERE id = ?
        """,
        (
            legacy_day.special_day,
            legacy_day.start_minute,
            legacy_day.end_minute,
            legacy_day.break_duration_minutes,
            expected,
            now,
            day_row["id"],
        ),
    )
    for position, pause in enumerate(legacy_day.breaks):
        db.execute(
            """
            INSERT INTO break_periods(
                public_id, day_entry_id, position, start_minute, end_minute,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                day_row["id"],
                position,
                pause.start_minute,
                pause.end_minute,
                now,
                now,
            ),
        )


def _legacy_opening(month: LegacyMonth, fallback: int) -> int:
    if not month.days:
        return fallback
    first = month.days[0]
    return first.running_balance_minutes - first.daily_overtime_minutes


def _close_legacy_month(db, month_row, legacy_month: LegacyMonth, opening: int, now: str):
    source_days = {item.work_date.isoformat(): item for item in legacy_month.days}
    running = opening
    all_days = db.execute(
        "SELECT id, work_date FROM day_entries WHERE month_id = ? ORDER BY work_date",
        (month_row["id"],),
    ).fetchall()
    for day_row in all_days:
        source_day = source_days.get(day_row["work_date"])
        if source_day is None:
            daily_overtime = 0
        else:
            daily_overtime = source_day.daily_overtime_minutes
            running = source_day.running_balance_minutes
        db.execute(
            """
            INSERT INTO closed_day_results(
                day_entry_id, daily_overtime_minutes, running_balance_minutes
            ) VALUES (?, ?, ?)
            """,
            (day_row["id"], daily_overtime, running),
        )

    guard = db.execute(
        """
        SELECT sql FROM sqlite_master
        WHERE type = 'trigger' AND name = 'month_close_guard'
        """
    ).fetchone()
    if guard is None or not guard["sql"]:
        raise StorageValidationError("The legacy import close guard is unavailable.")
    # SQLite DDL is transactional. Only legacy closure preconditions are deferred;
    # closed-record immutability triggers remain active and the exact guard is restored
    # before this transaction can commit.
    db.execute("DROP TRIGGER month_close_guard")
    db.execute(
        """
        UPDATE months SET status = 'closed', closing_balance_minutes = ?,
            closed_at = ?, updated_at = ?, revision = revision + 1 WHERE id = ?
        """,
        (running, now, now, month_row["id"]),
    )
    db.execute(guard["sql"])


def _source_schema_versions(preflight: LegacyPreflight) -> str:
    return ",".join(
        str(value)
        for value in sorted(
            {item.schema_version for item in preflight.months if item.schema_version}
        )
    ) or "legacy"


def _record_import(db, preflight: LegacyPreflight, now: str):
    db.execute(
        """
        INSERT INTO legacy_imports(
            source_fingerprint, manifest_digest, importer_version,
            source_schema_versions, file_count, month_count, day_count,
            warning_count, completed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            preflight.source_fingerprint,
            preflight.manifest_digest,
            VERSION,
            _source_schema_versions(preflight),
            preflight.file_count,
            len(preflight.months),
            sum(len(item.days) for item in preflight.months),
            len(preflight.warnings),
            now,
        ),
    )


def _validate_import(db):
    if db.execute("PRAGMA foreign_key_check").fetchone():
        raise StorageValidationError("Imported database failed foreign-key validation.")
    if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise StorageValidationError("Imported database failed integrity validation.")
    if db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'trigger' AND name = 'month_close_guard'"
    ).fetchone() is None:
        raise StorageValidationError("Imported database is missing its month-close guard.")
    if db.execute(
        """
        SELECT 1 FROM months month
        WHERE month.status = 'closed' AND (
            SELECT COUNT(*) FROM day_entries day WHERE day.month_id = month.id
        ) != (
            SELECT COUNT(*) FROM closed_day_results result
            JOIN day_entries day ON day.id = result.day_entry_id
            WHERE day.month_id = month.id
        )
        LIMIT 1
        """
    ).fetchone() is not None:
        raise StorageValidationError(
            "Imported closed month does not have one immutable result per day."
        )


def merge_preflight(
    repository: SQLiteRepository,
    preflight: LegacyPreflight,
) -> LegacyMergeResult:
    """Merge CSV history without replacing any authoritative local day."""
    if preflight.blocking_errors:
        raise StorageValidationError(
            f"Legacy import has {len(preflight.blocking_errors)} blocking error(s)."
        )
    if repository._connection.execute(
        "SELECT 1 FROM legacy_imports WHERE source_fingerprint = ?",
        (preflight.source_fingerprint,),
    ).fetchone():
        return LegacyMergeResult(
            preflight.source_root,
            True,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            len(preflight.warnings),
        )

    months_created = 0
    months_merged = 0
    months_closed = 0
    closures_kept_open = 0
    days_imported = 0
    days_kept_current = 0
    days_unchanged = 0
    now = _utc_text()
    try:
        with transaction(repository._connection) as db:
            if db.execute(
                "SELECT 1 FROM legacy_imports WHERE source_fingerprint = ?",
                (preflight.source_fingerprint,),
            ).fetchone():
                raise StorageValidationError("This exact CSV snapshot was already imported.")

            for legacy_month in preflight.months:
                month_row, created = _ensure_month(
                    repository, db, legacy_month.year, legacy_month.month, now
                )
                if created:
                    months_created += 1
                else:
                    months_merged += 1

                if month_row["status"] == "closed":
                    days_kept_current += sum(
                        _legacy_day_has_data(day, include_results=True)
                        for day in legacy_month.days
                    )
                    continue

                source_opening = _legacy_opening(
                    legacy_month, month_row["opening_balance_minutes"]
                )
                local_rows = db.execute(
                    "SELECT * FROM day_entries WHERE month_id = ? ORDER BY work_date",
                    (month_row["id"],),
                ).fetchall()
                month_had_local_data = any(
                    _local_day_has_data(db, row) for row in local_rows
                )
                month_conflicted = False
                source_by_date = {
                    item.work_date.isoformat(): item for item in legacy_month.days
                }
                for day_row in local_rows:
                    legacy_day = source_by_date.get(day_row["work_date"])
                    if legacy_day is None:
                        days_unchanged += 1
                        continue
                    if _local_day_has_data(db, day_row):
                        days_kept_current += 1
                        month_conflicted = True
                        continue
                    if not _legacy_day_has_data(
                        legacy_day, include_results=legacy_month.closed
                    ):
                        days_unchanged += 1
                        continue
                    fallback = day_row["expected_work_minutes"]
                    expected = (
                        _inferred_expected(legacy_day, fallback)
                        if created
                        else fallback
                    )
                    _apply_legacy_day(db, day_row, legacy_day, now, expected)
                    days_imported += 1

                if created or not month_had_local_data:
                    db.execute(
                        """
                        UPDATE months SET opening_balance_minutes = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (source_opening, now, month_row["id"]),
                    )
                    month_row = db.execute(
                        "SELECT * FROM months WHERE id = ?", (month_row["id"],)
                    ).fetchone()

                if legacy_month.closed:
                    if month_conflicted:
                        closures_kept_open += 1
                    else:
                        _close_legacy_month(
                            db,
                            month_row,
                            legacy_month,
                            month_row["opening_balance_minutes"],
                            now,
                        )
                        months_closed += 1

            _record_import(db, preflight, now)
            _validate_import(db)
    except sqlite3.Error as error:
        raise translate_error(error) from error

    return LegacyMergeResult(
        preflight.source_root,
        False,
        months_created,
        months_merged,
        months_closed,
        closures_kept_open,
        days_imported,
        days_kept_current,
        days_unchanged,
        len(preflight.warnings),
    )


def import_preflight(
    preflight: LegacyPreflight,
    destination: str | Path,
    *,
    default_workday_minutes: int = 480,
) -> SQLiteRepository:
    if preflight.blocking_errors:
        raise StorageValidationError(
            f"Legacy import has {len(preflight.blocking_errors)} blocking error(s)."
        )
    repository = SQLiteRepository.create(
        destination,
        default_workday_minutes=default_workday_minutes,
    )
    try:
        merge_preflight(repository, preflight)
        return repository
    except Exception:
        repository.close()
        raise
