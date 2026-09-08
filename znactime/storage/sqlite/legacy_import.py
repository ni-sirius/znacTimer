from __future__ import annotations

import sqlite3
import uuid
from dataclasses import replace
from datetime import date
from pathlib import Path

from znactime.config import VERSION
from znactime.core.constants import NO_DATA_DAY, NORMAL_DAY
from znactime.core.validation import special_day_text_problem
from znactime.storage.errors import StorageValidationError
from znactime.storage.legacy_csv_import import (
    CancellationCallback,
    LegacyDay,
    LegacyMergeResult,
    LegacyMonth,
    LegacyNormalization,
    LegacyPreflight,
    ProgressCallback,
    _cancel_if_requested,
    _report_progress,
)
from znactime.storage.sqlite.connection import transaction, translate_error
from znactime.storage.sqlite.repository import SQLiteRepository, _utc_text
from znactime.storage.sqlite.schema import schema_definition_mismatches


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
    """Return whether a day contains local user input that import must preserve."""
    if (
        day_row["local_input_revision"] > 0
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
    return False


def _ensure_month(repository: SQLiteRepository, db, year: int, month: int, now: str):
    dataset_id = repository._dataset_id(db)
    existing = db.execute(
        """
        SELECT id, dataset_id, year, month, status, opening_balance_minutes,
               revision
        FROM months WHERE dataset_id = ? AND year = ? AND month = ?
        """,
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
    repository._insert_calendar_days(db, month_id, year, month, now)
    return db.execute(
        """
        SELECT id, dataset_id, year, month, status, opening_balance_minutes,
               closing_balance_minutes, closed_at, created_at, updated_at, revision
        FROM months WHERE id = ?
        """,
        (month_id,),
    ).fetchone(), True


def _apply_legacy_day(db, day_row, legacy_day: LegacyDay, now: str, expected: int):
    special_day_problem = special_day_text_problem(legacy_day.special_day)
    if special_day_problem is not None:
        raise StorageValidationError(special_day_problem)
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
    db.executemany(
        """
        INSERT INTO break_periods(
            public_id, day_entry_id, position, start_minute, end_minute,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            (
                str(uuid.uuid4()),
                day_row["id"],
                position,
                pause.start_minute,
                pause.end_minute,
                now,
                now,
            )
            for position, pause in enumerate(legacy_day.breaks)
        ),
    )


def _legacy_opening(month: LegacyMonth, fallback: int) -> int:
    if not month.days:
        return fallback
    first = month.days[0]
    return first.running_balance_minutes - first.daily_overtime_minutes


def _normalization(
    day: LegacyDay,
    field: str,
    source_value,
    imported_value,
    reason: str,
) -> LegacyNormalization:
    return LegacyNormalization(
        day.work_date.isoformat(),
        field,
        source_value,
        imported_value,
        reason,
    )


def _normalize_legacy_day(
    day: LegacyDay,
) -> tuple[LegacyDay, tuple[LegacyNormalization, ...]]:
    """Return import-safe inputs that can be closed by the canonical guard."""
    changes = []
    invalid_window = (
        (day.start_minute is None) != (day.end_minute is None)
        or (
            day.start_minute is not None
            and day.end_minute is not None
            and day.end_minute <= day.start_minute
        )
    )
    start = day.start_minute
    end = day.end_minute
    duration = day.break_duration_minutes
    breaks = day.breaks
    if invalid_window:
        changes.append(
            _normalization(
                day,
                "work_interval",
                (start, end),
                (None, None),
                "Incomplete or non-positive legacy work interval was removed.",
            )
        )
        start = None
        end = None

    if start is None:
        if duration not in (None, 0) or breaks:
            changes.append(
                _normalization(
                    day,
                    "interruptions",
                    (duration, breaks),
                    (0, ()),
                    "Interruptions without a valid work interval were removed.",
                )
            )
        duration = 0
        breaks = ()
    elif duration is not None:
        if duration > end - start:
            changes.append(
                _normalization(
                    day,
                    "break_duration_minutes",
                    duration,
                    0,
                    "Break duration exceeded the work interval and was removed.",
                )
            )
            duration = 0
    elif any(
        pause.end_minute is None
        or pause.start_minute < start
        or pause.end_minute > end
        for pause in breaks
    ):
        changes.append(
            _normalization(
                day,
                "break_periods",
                breaks,
                (),
                "Active or out-of-range legacy pauses were removed.",
            )
        )
        breaks = ()

    return (
        replace(
            day,
            start_minute=start,
            end_minute=end,
            break_duration_minutes=duration,
            breaks=breaks,
        ),
        tuple(changes),
    )


def _close_legacy_month(
    repository: SQLiteRepository,
    db,
    month_row,
    legacy_month: LegacyMonth,
    now: str,
    *,
    cancelled: CancellationCallback | None,
) -> tuple[LegacyNormalization, ...]:
    unresolved = repository._unresolved_close_days(db, month_row["id"])
    if unresolved:
        no_data_minutes = tuple(
            repository._expected_minutes(
                date.fromisoformat(row["work_date"]), NO_DATA_DAY, db
            )
            for row in unresolved
        )
        db.executemany(
            """
            UPDATE day_entries SET special_day = ?, expected_work_minutes = ?,
                expected_minutes_overridden = 0, updated_at = ?,
                revision = revision + 1
            WHERE id = ?
            """,
            (
                (NO_DATA_DAY, minutes, now, row["id"])
                for row, minutes in zip(unresolved, no_data_minutes)
            ),
        )
        if repository._unresolved_close_days(db, month_row["id"]):
            raise StorageValidationError(
                "Imported No data rows still require planned work under the special-day schedule."
            )
    calculated = repository._close_month_in_transaction(
        db,
        month_row,
        before_day=lambda: _cancel_if_requested(cancelled),
        now=now,
    )
    source_days = {item.work_date.isoformat(): item for item in legacy_month.days}
    changes = [
        LegacyNormalization(
            row["work_date"],
            "special_day",
            row["special_day"],
            NO_DATA_DAY,
            "A blank normal day was explicitly classified so the imported month is complete.",
        )
        for row in unresolved
    ]
    for work_date, daily_overtime, running_balance in calculated:
        source_day = source_days.get(work_date)
        if source_day is None:
            continue
        if source_day.daily_overtime_minutes != daily_overtime:
            changes.append(
                _normalization(
                    source_day,
                    "daily_overtime_minutes",
                    source_day.daily_overtime_minutes,
                    daily_overtime,
                    "Derived overtime was recalculated from normalized day inputs.",
                )
            )
        if source_day.running_balance_minutes != running_balance:
            changes.append(
                _normalization(
                    source_day,
                    "running_balance_minutes",
                    source_day.running_balance_minutes,
                    running_balance,
                    "Running balance was recalculated from the canonical overtime chain.",
                )
            )
    if legacy_month.days and calculated:
        source_closing = legacy_month.days[-1].running_balance_minutes
        imported_closing = calculated[-1][2]
        if source_closing != imported_closing:
            changes.append(
                LegacyNormalization(
                    f"{legacy_month.year:04d}-{legacy_month.month:02d}",
                    "closing_balance_minutes",
                    source_closing,
                    imported_closing,
                    "Closing balance was aligned with the recalculated result chain.",
                )
            )
    return tuple(changes)


def _closure_block_reason(db, month_row) -> str | None:
    today = date.today()
    if (month_row["year"], month_row["month"]) > (today.year, today.month):
        return "A future month cannot be closed, so this imported month remained open."
    if db.execute(
        """
        SELECT 1 FROM months prior_open
        WHERE prior_open.dataset_id = ? AND prior_open.status = 'open'
          AND prior_open.year * 12 + prior_open.month < ? * 12 + ?
          AND prior_open.year * 12 + prior_open.month > COALESCE(
              (
                  SELECT MAX(prior_closed.year * 12 + prior_closed.month)
                  FROM months prior_closed
                  WHERE prior_closed.dataset_id = prior_open.dataset_id
                    AND prior_closed.status = 'closed'
                    AND prior_closed.year * 12 + prior_closed.month < ? * 12 + ?
              ),
              0
          )
        LIMIT 1
        """,
        (
            month_row["dataset_id"],
            month_row["year"],
            month_row["month"],
            month_row["year"],
            month_row["month"],
        ),
    ).fetchone():
        return "An earlier month is still open, so this imported month remained open."
    return None


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
    mismatches = schema_definition_mismatches(db)
    if mismatches:
        names = ", ".join(name for _object_type, name in mismatches)
        raise StorageValidationError(
            f"Imported database does not retain its canonical schema: {names}."
        )
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
    *,
    progress: ProgressCallback | None = None,
    cancelled: CancellationCallback | None = None,
    before_commit=None,
) -> LegacyMergeResult:
    """Merge CSV history without replacing any authoritative local day."""
    if preflight.blocking_errors:
        raise StorageValidationError(
            f"Legacy import has {len(preflight.blocking_errors)} blocking error(s)."
        )
    _cancel_if_requested(cancelled)
    repository._connection.set_progress_handler(
        lambda: int(bool(cancelled and cancelled())),
        1_000,
    )

    months_created = 0
    months_merged = 0
    months_closed = 0
    closures_kept_open = 0
    days_imported = 0
    days_kept_current = 0
    days_unchanged = 0
    normalizations: list[LegacyNormalization] = []
    completed_result = None
    now = _utc_text()
    try:
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
        with transaction(repository._connection) as db:
            if db.execute(
                "SELECT 1 FROM legacy_imports WHERE source_fingerprint = ?",
                (preflight.source_fingerprint,),
            ).fetchone():
                raise StorageValidationError("This exact CSV snapshot was already imported.")

            for month_index, legacy_month in enumerate(preflight.months, 1):
                _cancel_if_requested(cancelled)
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
                    """
                    SELECT id, work_date, special_day, start_minute, end_minute,
                           break_duration_minutes, expected_work_minutes,
                           expected_minutes_overridden, local_input_revision
                    FROM day_entries WHERE month_id = ? ORDER BY work_date
                    """,
                    (month_row["id"],),
                ).fetchall()
                month_had_local_data = any(
                    _local_day_has_data(db, row) for row in local_rows
                )
                month_conflicted = month_had_local_data
                source_by_date = {
                    item.work_date.isoformat(): item for item in legacy_month.days
                }
                for day_row in local_rows:
                    _cancel_if_requested(cancelled)
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
                    normalized_day, day_normalizations = _normalize_legacy_day(
                        legacy_day
                    )
                    fallback = repository._expected_minutes(
                        normalized_day.work_date,
                        normalized_day.special_day,
                        db,
                    )
                    expected = _inferred_expected(normalized_day, fallback)
                    _apply_legacy_day(db, day_row, normalized_day, now, expected)
                    normalizations.extend(day_normalizations)
                    days_imported += 1

                if created or not month_had_local_data:
                    previous_year, previous_month = (
                        (legacy_month.year, legacy_month.month - 1)
                        if legacy_month.month > 1
                        else (legacy_month.year - 1, 12)
                    )
                    previous = db.execute(
                        """
                        SELECT closing_balance_minutes FROM months
                        WHERE dataset_id = ? AND year = ? AND month = ?
                          AND status = 'closed'
                        """,
                        (
                            month_row["dataset_id"],
                            previous_year,
                            previous_month,
                        ),
                    ).fetchone()
                    target_opening = (
                        previous["closing_balance_minutes"]
                        if previous is not None
                        else source_opening
                    )
                    if target_opening != source_opening:
                        normalizations.append(
                            LegacyNormalization(
                                f"{legacy_month.year:04d}-{legacy_month.month:02d}",
                                "opening_balance_minutes",
                                source_opening,
                                target_opening,
                                "Opening balance was aligned with the preceding closed month.",
                            )
                        )
                    db.execute(
                        """
                        UPDATE months SET opening_balance_minutes = ?, updated_at = ?,
                            revision = revision + 1
                        WHERE id = ? AND opening_balance_minutes != ?
                        """,
                        (target_opening, now, month_row["id"], target_opening),
                    )
                    month_row = db.execute(
                        """
                        SELECT id, dataset_id, year, month, status,
                               opening_balance_minutes, revision
                        FROM months WHERE id = ?
                        """,
                        (month_row["id"],),
                    ).fetchone()

                if legacy_month.closed:
                    closure_block = (
                        "Local day data was preserved, so the imported month remained open."
                        if month_conflicted
                        else _closure_block_reason(db, month_row)
                    )
                    if closure_block is not None:
                        closures_kept_open += 1
                        normalizations.append(
                            LegacyNormalization(
                                f"{legacy_month.year:04d}-{legacy_month.month:02d}",
                                "status",
                                "closed",
                                "open",
                                closure_block,
                            )
                        )
                    else:
                        normalizations.extend(_close_legacy_month(
                            repository,
                            db,
                            month_row,
                            legacy_month,
                            now,
                            cancelled=cancelled,
                        ))
                        months_closed += 1

                _report_progress(
                    progress,
                    "Importing legacy months",
                    month_index,
                    len(preflight.months),
                )

            _cancel_if_requested(cancelled)
            _report_progress(progress, "Validating imported database", 0, 0)
            _record_import(db, preflight, now)
            _validate_import(db)
            completed_result = LegacyMergeResult(
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
                tuple(normalizations),
            )
            if before_commit is not None:
                completed_result = before_commit(completed_result)
    except sqlite3.Error as error:
        _cancel_if_requested(cancelled)
        raise translate_error(error) from error
    except Exception:
        _cancel_if_requested(cancelled)
        raise
    finally:
        repository._connection.set_progress_handler(None, 0)

    if completed_result is None:
        raise StorageValidationError("Legacy import completed without an outcome record.")
    return completed_result


def import_preflight(
    preflight: LegacyPreflight,
    destination: str | Path,
    *,
    default_workday_minutes: int = 480,
    progress: ProgressCallback | None = None,
    cancelled: CancellationCallback | None = None,
    log_database_path: str | Path | None = None,
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
        repository.merge_legacy(
            preflight,
            progress=progress,
            cancelled=cancelled,
            log_database_path=log_database_path,
        )
        return repository
    except Exception:
        repository.close()
        raise
