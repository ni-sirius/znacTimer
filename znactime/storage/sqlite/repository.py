from __future__ import annotations

import calendar
import os
import sqlite3
import tempfile
import uuid
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

from znactime.config import VERSION
from znactime.core.constants import (
    NO_DATA_DAY,
    NORMAL_DAY,
    effective_expected_work_minutes,
    is_normal_day,
)
from znactime.core.models import (
    BreakRecord,
    DayRecord,
    MonthClosePreview,
    MonthRecord,
    WorkSchedulePeriod,
)
from znactime.core.validation import special_day_text_problem
from znactime.storage.errors import (
    ClosedPeriodError,
    StorageConflict,
    StorageCorrupt,
    StorageError,
    StorageUnavailable,
    StorageValidationError,
    StorageVersionUnsupported,
)
from znactime.storage.atomic_file import (
    _sync_parent_directory,
    publish_staged_file,
    reject_protected_destination,
    sqlite_protected_paths,
)
from znactime.storage.sqlite.connection import (
    connect_database,
    create_database,
    read_transaction,
    require_changed,
    transaction,
    translate_error,
)
from znactime.storage.sqlite.migrations import MIGRATIONS, migration_signature
from znactime.storage.sqlite.schema import (
    SCHEMA_SQL,
    SCHEMA_VERSION,
    schema_manifest,
    schema_definition_mismatches,
)


_SCHEDULE_COLUMNS = (
    "monday_minutes",
    "tuesday_minutes",
    "wednesday_minutes",
    "thursday_minutes",
    "friday_minutes",
    "saturday_minutes",
    "sunday_minutes",
)

_MINIMUM_SQLITE_VERSION = (3, 37, 0)


def _utc_text(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)
    _require_aware_datetime(value)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _require_aware_datetime(value: datetime) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise StorageValidationError(
            "Repository timestamps must include an explicit timezone."
        )


def _uuid4() -> str:
    return str(uuid.uuid4())


def _repository_operation(method):
    """Keep adapter/OS exceptions behind the public repository contract."""
    @wraps(method)
    def guarded(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except StorageError:
            raise
        except sqlite3.Error as error:
            raise translate_error(error) from error
        except OSError as error:
            raise StorageUnavailable(
                "The time database filesystem operation failed."
            ) from error

    return guarded


def _stored_date(value, field: str) -> date:
    if not isinstance(value, str):
        raise StorageCorrupt(f"The database contains an invalid {field} value.")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise StorageCorrupt(
            f"The database contains an invalid {field} value."
        ) from error


def _validate_uuid4(value: str) -> str:
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, TypeError, ValueError) as error:
        raise StorageValidationError("Public identity must be a canonical UUIDv4.") from error
    canonical = str(parsed)
    if parsed.version != 4 or value != canonical:
        raise StorageValidationError("Public identity must be a canonical UUIDv4.")
    return canonical


def _validate_minute(value: int | None, *, allow_1440: bool = False):
    upper = 1440 if allow_1440 else 1439
    if value is not None and (not isinstance(value, int) or not 0 <= value <= upper):
        raise StorageValidationError(f"Minute value must be between 0 and {upper}.")


def _validate_work_range(start_minute: int | None, end_minute: int | None) -> None:
    if end_minute is None:
        return
    if start_minute is None:
        raise StorageValidationError("An end time requires a start time.")
    if end_minute <= start_minute:
        raise StorageValidationError(
            "End time must be later than start time; overnight work is not supported."
        )


def _validate_break_layout(breaks: tuple[BreakRecord, ...]) -> None:
    ordered = []
    for pause in breaks:
        _validate_minute(pause.start_minute)
        _validate_minute(pause.end_minute)
        if pause.start_minute is None:
            raise StorageValidationError("A break requires a start time.")
        if pause.end_minute is not None and pause.end_minute <= pause.start_minute:
            raise StorageValidationError("A break end must be later than its start.")
        ordered.append(pause)

    ordered.sort(key=lambda pause: pause.start_minute)
    for previous, current in zip(ordered, ordered[1:]):
        if previous.end_minute is None or current.start_minute < previous.end_minute:
            raise StorageValidationError("Break periods cannot overlap.")


def _month_index(year: int, month: int) -> int:
    return year * 12 + month


def _unresolved_normal_day(row) -> bool:
    if not is_normal_day(row["special_day"]):
        return False
    if row["start_minute"] is not None or row["end_minute"] is not None:
        return False
    return not (
        row["expected_work_minutes"] == 0
        and _stored_date(row["work_date"], "work date").weekday() >= 5
    )


def _migration_statements(script: str):
    """Yield complete SQLite statements without breaking trigger bodies."""
    pending: list[str] = []
    for line in script.splitlines(keepends=True):
        pending.append(line)
        candidate = "".join(pending)
        if sqlite3.complete_statement(candidate):
            statement = candidate.strip()
            if statement:
                yield statement
            pending.clear()
    if "".join(pending).strip():
        raise StorageValidationError("Database migration contains incomplete SQL.")


class SQLiteRepository:
    def __init__(self, path: str | Path):
        self._require_supported_sqlite()
        self.path = Path(path).resolve()
        self._last_import_log_path: Path | None = None
        self._dataset_id_value: int | None = None
        self._connection = connect_database(self.path)
        migration_backup = None
        try:
            migration_backup = self._upgrade_schema()
            if migration_backup is not None:
                # Reopening proves that the committed file can be opened cleanly,
                # independently of the connection that performed the migration.
                self._connection.close()
                self._connection = connect_database(self.path)
            dataset_id = self._verify_version()
            if migration_backup is not None:
                self._remove_migration_backup(migration_backup)
            self._dataset_id_value = dataset_id
        except Exception as error:
            if migration_backup is not None:
                self._add_recovery_location(error, migration_backup)
            self._connection.close()
            raise

    @classmethod
    @_repository_operation
    def create(
        cls,
        path: str | Path,
        *,
        default_workday_minutes: int = 480,
        dataset_public_id: str | None = None,
    ) -> "SQLiteRepository":
        cls._require_supported_sqlite()
        _validate_minute(default_workday_minutes, allow_1440=True)
        if dataset_public_id is not None:
            dataset_public_id = _validate_uuid4(dataset_public_id)
        target = Path(path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        connection = create_database(target)
        try:
            if connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' LIMIT 1"
            ).fetchone():
                raise StorageConflict("The target database is not empty.")
            now = _utc_text()
            with transaction(connection) as db:
                for statement in _migration_statements(SCHEMA_SQL):
                    db.execute(statement)
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at, app_version) VALUES (?, ?, ?)",
                    (SCHEMA_VERSION, now, VERSION),
                )
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                dataset_id = connection.execute(
                    "INSERT INTO datasets(public_id, created_at) VALUES (?, ?)",
                    (dataset_public_id or _uuid4(), now),
                ).lastrowid
                values = (default_workday_minutes,) * 5 + (0, 0)
                connection.execute(
                    f"""
                    INSERT INTO work_schedule_periods(
                        public_id, dataset_id, effective_from, effective_to,
                        {', '.join(_SCHEDULE_COLUMNS)}, created_at, updated_at
                    ) VALUES (?, ?, '0001-01-01', NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (_uuid4(), dataset_id, *values, now, now),
                )
                cls._verify_current_database(connection)
        except sqlite3.Error as error:
            raise translate_error(error) from error
        finally:
            connection.close()
        return cls(target)

    @staticmethod
    def _require_supported_sqlite():
        if sqlite3.sqlite_version_info < _MINIMUM_SQLITE_VERSION:
            installed = ".".join(str(item) for item in sqlite3.sqlite_version_info)
            required = ".".join(str(item) for item in _MINIMUM_SQLITE_VERSION)
            raise StorageVersionUnsupported(
                f"SQLite {required} or newer is required; Python provides {installed}."
            )

    def _verify_version(self) -> int:
        return self._verify_current_database(self._connection)

    @staticmethod
    def _verify_current_database(connection: sqlite3.Connection) -> int:
        schema_mismatches = ()
        try:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            schema_mismatches = schema_definition_mismatches(connection)
            migration = connection.execute(
                "SELECT MAX(version) FROM schema_migrations"
            ).fetchone()[0]
        except sqlite3.Error as error:
            if schema_mismatches:
                names = ", ".join(name for _type, name in schema_mismatches)
                raise StorageCorrupt(
                    f"The time database schema definitions are incomplete: {names}."
                ) from error
            raise translate_error(error) from error
        if version != SCHEMA_VERSION or migration != SCHEMA_VERSION:
            raise StorageVersionUnsupported(
                f"Database schema {version!r}/{migration!r} is not supported."
            )
        if schema_mismatches:
            names = ", ".join(name for _object_type, name in schema_mismatches)
            raise StorageCorrupt(
                f"The time database schema definitions do not match version "
                f"{SCHEMA_VERSION}: {names}."
            )
        try:
            if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise StorageCorrupt("The time database failed its startup integrity check.")
            if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise StorageCorrupt("The time database contains invalid relationships.")
            datasets = connection.execute("SELECT id FROM datasets LIMIT 2").fetchall()
            if len(datasets) != 1:
                raise StorageCorrupt("The database must contain exactly one dataset.")
            return datasets[0][0]
        except sqlite3.Error as error:
            raise translate_error(error) from error

    def _upgrade_schema(self):
        try:
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            migration = self._connection.execute(
                "SELECT MAX(version) FROM schema_migrations"
            ).fetchone()[0]
        except sqlite3.Error as error:
            mismatches = schema_definition_mismatches(self._connection)
            if mismatches:
                names = ", ".join(name for _type, name in mismatches)
                raise StorageCorrupt(
                    f"The time database schema definitions are incomplete: {names}."
                ) from error
            raise translate_error(error) from error

        if version == SCHEMA_VERSION and migration == SCHEMA_VERSION:
            return None
        if version != migration or version not in MIGRATIONS:
            return None

        backup_path = self._create_migration_backup(version, migration)
        rebuilds_referenced_tables = version <= 4 < SCHEMA_VERSION
        try:
            if rebuilds_referenced_tables:
                # SQLite cannot rebuild referenced tables while FK enforcement
                # is enabled.  Keep dependent FK declarations pointed at the
                # canonical table names while the v4 migration renames the old
                # tables, then verify every relationship before committing.
                self._connection.execute("PRAGMA foreign_keys = OFF")
                self._connection.execute("PRAGMA legacy_alter_table = ON")
            with transaction(self._connection) as db:
                while version < SCHEMA_VERSION:
                    migration_sql = MIGRATIONS.get(version)
                    if migration_sql is None:
                        raise StorageVersionUnsupported(
                            f"No migration is available from database schema {version}."
                        )
                    self._validate_migration_source(version)
                    for statement in _migration_statements(migration_sql):
                        if (
                            version == 3
                            and statement.startswith(
                                "ALTER TABLE day_entries ADD COLUMN local_input_revision"
                            )
                            and any(
                                row["name"] == "local_input_revision"
                                for row in db.execute(
                                    "PRAGMA table_info(day_entries)"
                                ).fetchall()
                            )
                        ):
                            continue
                        db.execute(statement)
                    version += 1
                    db.execute(
                        "INSERT INTO schema_migrations(version, applied_at, app_version) "
                        "VALUES (?, ?, ?)",
                        (version, _utc_text(), VERSION),
                    )
                    db.execute(f"PRAGMA user_version = {version}")

                # Validate the finished schema and data before the transaction
                # is allowed to commit.
                self._verify_version()
        except Exception as error:
            self._add_recovery_location(error, backup_path)
            raise
        finally:
            if rebuilds_referenced_tables:
                self._connection.execute("PRAGMA legacy_alter_table = OFF")
                self._connection.execute("PRAGMA foreign_keys = ON")
        return backup_path

    @_repository_operation
    def _create_migration_backup(self, version: int, migration: int) -> Path:
        recovery_root = self.path.parent / "recovery"
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup_directory = recovery_root / (
            f"schema-v{version}-to-v{SCHEMA_VERSION}-{stamp}-{uuid.uuid4().hex[:8]}"
        )
        backup_path = backup_directory / self.path.name
        backup = None
        try:
            recovery_root.mkdir(parents=True, exist_ok=True)
            backup_directory.mkdir(mode=0o700)
            backup = create_database(backup_path)
            self._connection.backup(backup)
            if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise StorageCorrupt(
                    "The pre-migration database backup failed its integrity check."
                )
            if backup.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise StorageCorrupt(
                    "The pre-migration database backup contains invalid relationships."
                )
            backup_version = backup.execute("PRAGMA user_version").fetchone()[0]
            backup_migration = backup.execute(
                "SELECT MAX(version) FROM schema_migrations"
            ).fetchone()[0]
            if backup_version != version or backup_migration != migration:
                raise StorageCorrupt(
                    "The pre-migration database backup has inconsistent version metadata."
                )
            if schema_manifest(backup) != schema_manifest(self._connection):
                raise StorageCorrupt(
                    "The pre-migration database backup does not match the source schema."
                )
            backup.close()
            backup = None
            # Windows requires a writable file handle for FlushFileBuffers,
            # which is what os.fsync delegates to there.
            with backup_path.open("r+b") as handle:
                os.fsync(handle.fileno())
            _sync_parent_directory(backup_directory)
            _sync_parent_directory(recovery_root)
            return backup_path
        except Exception:
            if backup is not None:
                backup.close()
            for suffix in ("-journal", "-wal", "-shm", ""):
                try:
                    backup_path.with_name(backup_path.name + suffix).unlink()
                except FileNotFoundError:
                    pass
                except OSError:
                    pass
            try:
                backup_directory.rmdir()
            except OSError:
                pass
            raise

    @_repository_operation
    def _remove_migration_backup(self, backup_path: Path) -> None:
        recovery_root = (self.path.parent / "recovery").resolve()
        resolved_backup = backup_path.resolve()
        if (
            resolved_backup.name != self.path.name
            or resolved_backup.parent.parent != recovery_root
        ):
            raise StorageUnavailable(
                "The verified migration backup path is outside the recovery directory."
            )
        resolved_backup.unlink()
        _sync_parent_directory(resolved_backup.parent)
        resolved_backup.parent.rmdir()
        _sync_parent_directory(recovery_root)

    @staticmethod
    def _add_recovery_location(error: Exception, backup_path: Path) -> None:
        recovery_text = f"Recovery backup: {backup_path}"
        error.recovery_backup_path = backup_path
        error.migration_signature = migration_signature()
        if recovery_text not in str(error):
            message = str(error)
            error.args = (
                f"{message} {recovery_text}" if message else recovery_text,
                *error.args[1:],
            )

    def _validate_migration_source(self, version: int) -> None:
        if version != 2:
            return
        invalid_schedule = self._connection.execute(
            """
            SELECT 1 FROM work_schedule_periods
            WHERE date(effective_from, '+0 days') IS NULL
               OR effective_from != date(effective_from, '+0 days')
               OR (effective_to IS NOT NULL AND (
                   date(effective_to, '+0 days') IS NULL
                   OR effective_to != date(effective_to, '+0 days')
               ))
            LIMIT 1
            """
        ).fetchone()
        invalid_day = self._connection.execute(
            """
            SELECT 1 FROM day_entries
            WHERE date(work_date, '+0 days') IS NULL
               OR work_date != date(work_date, '+0 days')
            LIMIT 1
            """
        ).fetchone()
        if invalid_schedule is not None or invalid_day is not None:
            raise StorageCorrupt(
                "The database contains a malformed calendar date and cannot be upgraded."
            )

    def _dataset_id(self, connection=None) -> int:
        if self._dataset_id_value is None:
            raise StorageCorrupt("The repository dataset identity is unavailable.")
        return self._dataset_id_value

    def _expected_minutes_for_dates(
        self,
        work_dates: tuple[date, ...],
        connection=None,
    ) -> tuple[int, ...]:
        if not work_dates:
            return ()
        db = connection or self._connection
        first = min(work_dates).isoformat()
        last = max(work_dates).isoformat()
        schedules = db.execute(
            f"""
            SELECT effective_from, effective_to, {', '.join(_SCHEDULE_COLUMNS)}
            FROM work_schedule_periods
            WHERE dataset_id = ? AND effective_from <= ?
              AND (effective_to IS NULL OR effective_to >= ?)
            ORDER BY effective_from DESC
            """,
            (self._dataset_id(), last, first),
        ).fetchall()
        values = []
        for work_date in work_dates:
            work_date_text = work_date.isoformat()
            schedule = next(
                (
                    row
                    for row in schedules
                    if row["effective_from"] <= work_date_text
                    and (
                        row["effective_to"] is None
                        or row["effective_to"] >= work_date_text
                    )
                ),
                None,
            )
            if schedule is None:
                raise StorageValidationError(
                    f"No work schedule applies to {work_date_text}."
                )
            values.append(schedule[_SCHEDULE_COLUMNS[work_date.weekday()]])
        return tuple(values)

    def _expected_minutes(self, work_date: date, connection=None) -> int:
        return self._expected_minutes_for_dates((work_date,), connection)[0]

    def _insert_calendar_days(
        self,
        db: sqlite3.Connection,
        month_id: int,
        year: int,
        month: int,
        now: str,
    ) -> None:
        work_dates = tuple(
            date(year, month, day_number)
            for day_number in range(1, calendar.monthrange(year, month)[1] + 1)
        )
        expected_minutes = self._expected_minutes_for_dates(work_dates, db)
        db.executemany(
            """
            INSERT INTO day_entries(
                month_id, work_date, special_day, start_minute, end_minute,
                break_duration_minutes, expected_work_minutes,
                expected_minutes_overridden, created_at, updated_at
            ) VALUES (?, ?, ?, NULL, NULL, 0, ?, 0, ?, ?)
            """,
            (
                (month_id, work_date.isoformat(), NORMAL_DAY, expected, now, now)
                for work_date, expected in zip(work_dates, expected_minutes)
            ),
        )

    @staticmethod
    def _day_overtime_minutes(row) -> int:
        start = row["start_minute"]
        end = row["end_minute"]
        if start is None or end is None or end <= start:
            return 0
        interruption = row["interruption_minutes"]
        if interruption is None or interruption < 0 or interruption > end - start:
            return 0
        expected = effective_expected_work_minutes(
            row["special_day"], row["expected_work_minutes"]
        )
        return end - start - interruption - expected

    @staticmethod
    def _calculation_rows(db, *, month_id: int | None = None, where="", parameters=()):
        month_filter = "day.month_id = ?" if month_id is not None else where
        values = (month_id,) if month_id is not None else tuple(parameters)
        return db.execute(
            f"""
            SELECT day.id, day.work_date, day.special_day, day.start_minute,
                   day.end_minute, day.expected_work_minutes,
                   CASE
                       WHEN day.break_duration_minutes IS NOT NULL
                           THEN day.break_duration_minutes
                       WHEN COUNT(pause.id) = 0 THEN 0
                       WHEN SUM(pause.end_minute IS NULL) > 0 THEN NULL
                       ELSE SUM(pause.end_minute - pause.start_minute)
                   END AS interruption_minutes
            FROM day_entries day
            JOIN months month ON month.id = day.month_id
            LEFT JOIN break_periods pause ON pause.day_entry_id = day.id
            WHERE {month_filter}
            GROUP BY day.id
            ORDER BY day.work_date
            """,
            values,
        ).fetchall()

    def _derived_opening_balance(self, db, year: int, month: int) -> int:
        target = _month_index(year, month)
        checkpoint = db.execute(
            """
            SELECT year, month, closing_balance_minutes
            FROM months
            WHERE dataset_id = ? AND status = 'closed'
              AND year * 12 + month < ?
            ORDER BY year DESC, month DESC LIMIT 1
            """,
            (self._dataset_id(db), target),
        ).fetchone()
        if checkpoint is None:
            anchor = db.execute(
                """
                SELECT year, month, opening_balance_minutes
                FROM months
                WHERE dataset_id = ? AND year * 12 + month <= ?
                ORDER BY year, month LIMIT 1
                """,
                (self._dataset_id(db), target),
            ).fetchone()
            if anchor is None:
                return 0
            checkpoint_index = _month_index(anchor["year"], anchor["month"]) - 1
            running = anchor["opening_balance_minutes"]
        else:
            checkpoint_index = _month_index(checkpoint["year"], checkpoint["month"])
            running = checkpoint["closing_balance_minutes"]
        rows = self._calculation_rows(
            db,
            where=(
                "month.dataset_id = ? AND month.status = 'open' "
                "AND month.year * 12 + month.month > ? "
                "AND month.year * 12 + month.month < ?"
            ),
            parameters=(self._dataset_id(db), checkpoint_index, target),
        )
        return running + sum(self._day_overtime_minutes(row) for row in rows)

    def _refresh_open_month_carry(self, year: int, month: int) -> None:
        with transaction(self._connection) as db:
            row = db.execute(
                """
                SELECT id, status, opening_balance_minutes FROM months
                WHERE dataset_id = ? AND year = ? AND month = ?
                """,
                (self._dataset_id(db), year, month),
            ).fetchone()
            if row is None or row["status"] != "open":
                return
            opening = self._derived_opening_balance(db, year, month)
            if opening != row["opening_balance_minutes"]:
                now = _utc_text()
                db.execute(
                    """
                    UPDATE months SET opening_balance_minutes = ?, updated_at = ?,
                        revision = revision + 1 WHERE id = ?
                    """,
                    (opening, now, row["id"]),
                )

    @_repository_operation
    def get_or_create_month(self, year: int, month: int) -> MonthRecord:
        try:
            date(year, month, 1)
        except (TypeError, ValueError) as error:
            raise StorageValidationError("Invalid calendar month.") from error
        existing = self.load_month(year, month)
        if existing is not None:
            if existing.status == "open":
                self._refresh_open_month_carry(year, month)
                refreshed = self.load_month(year, month)
                if refreshed is None:
                    raise StorageCorrupt("The selected month disappeared while loading.")
                return refreshed
            return existing
        now = _utc_text()
        with transaction(self._connection) as db:
            dataset_id = self._dataset_id(db)
            existing_id = db.execute(
                """
                SELECT id FROM months
                WHERE dataset_id = ? AND year = ? AND month = ?
                """,
                (dataset_id, year, month),
            ).fetchone()
            if existing_id is None:
                previous_year, previous_month = (
                    (year, month - 1) if month > 1 else (year - 1, 12)
                )
                previous = db.execute(
                    """
                    SELECT closing_balance_minutes FROM months
                    WHERE dataset_id = ? AND year = ? AND month = ?
                      AND status = 'closed'
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
                self._insert_calendar_days(db, month_id, year, month, now)
        self._refresh_open_month_carry(year, month)
        result = self.load_month(year, month)
        if result is None:
            raise StorageCorrupt("The newly created month disappeared before it was loaded.")
        return result

    @_repository_operation
    def load_month(self, year: int, month: int) -> MonthRecord | None:
        with read_transaction(self._connection) as db:
            records = self._load_month_records(db, year=year, month=month)
            return records[0] if records else None

    @_repository_operation
    def list_months(self, year: int | None = None) -> tuple[MonthRecord, ...]:
        with read_transaction(self._connection) as db:
            return self._load_month_records(db, year=year)

    def _load_month_records(
        self,
        db,
        *,
        year: int | None = None,
        month: int | None = None,
    ) -> tuple[MonthRecord, ...]:
        conditions = ["month.dataset_id = ?"]
        parameters: list[int] = [self._dataset_id(db)]
        if year is not None:
            conditions.append("month.year = ?")
            parameters.append(year)
        if month is not None:
            conditions.append("month.month = ?")
            parameters.append(month)
        where = " AND ".join(conditions)

        month_rows = db.execute(
            f"""
            SELECT month.id, month.year, month.month, month.status,
                   month.opening_balance_minutes, month.closing_balance_minutes,
                   month.revision
            FROM months month
            WHERE {where}
            ORDER BY month.year, month.month
            """,
            parameters,
        ).fetchall()
        if not month_rows:
            return ()

        day_rows = db.execute(
            f"""
            SELECT day.id, day.month_id, day.work_date, day.special_day,
                   day.start_minute, day.end_minute, day.break_duration_minutes,
                   day.expected_work_minutes, day.expected_minutes_overridden,
                   day.revision
            FROM day_entries day
            JOIN months month ON month.id = day.month_id
            WHERE {where}
            ORDER BY month.year, month.month, day.work_date
            """,
            parameters,
        ).fetchall()
        pause_rows = db.execute(
            f"""
            SELECT pause.day_entry_id, pause.public_id, pause.position,
                   pause.start_minute, pause.end_minute, pause.revision
            FROM break_periods pause
            JOIN day_entries day ON day.id = pause.day_entry_id
            JOIN months month ON month.id = day.month_id
            WHERE {where}
            ORDER BY month.year, month.month, day.work_date, pause.position
            """,
            parameters,
        ).fetchall()
        result_rows = db.execute(
            f"""
            SELECT result.day_entry_id, result.daily_overtime_minutes,
                   result.running_balance_minutes
            FROM closed_day_results result
            JOIN day_entries day ON day.id = result.day_entry_id
            JOIN months month ON month.id = day.month_id
            WHERE {where}
            ORDER BY month.year, month.month, day.work_date
            """,
            parameters,
        ).fetchall()

        breaks_by_day: dict[int, list[BreakRecord]] = {}
        for pause in pause_rows:
            breaks_by_day.setdefault(pause["day_entry_id"], []).append(
                BreakRecord(
                    public_id=pause["public_id"],
                    position=pause["position"],
                    start_minute=pause["start_minute"],
                    end_minute=pause["end_minute"],
                    revision=pause["revision"],
                )
            )
        results_by_day = {row["day_entry_id"]: row for row in result_rows}
        days_by_month: dict[int, list[DayRecord]] = {}
        for day in day_rows:
            days_by_month.setdefault(day["month_id"], []).append(
                self._day_from_row(
                    day,
                    breaks=tuple(breaks_by_day.get(day["id"], ())),
                    result=results_by_day.get(day["id"]),
                )
            )
        return tuple(
            MonthRecord(
                year=row["year"],
                month=row["month"],
                status=row["status"],
                opening_balance_minutes=row["opening_balance_minutes"],
                closing_balance_minutes=row["closing_balance_minutes"],
                revision=row["revision"],
                days=tuple(days_by_month.get(row["id"], ())),
            )
            for row in month_rows
        )

    def _day_from_row(self, row, *, breaks=(), result=None) -> DayRecord:
        special_day_problem = special_day_text_problem(row["special_day"])
        if special_day_problem is not None:
            raise StorageCorrupt(
                f"The database contains invalid special-day text: {special_day_problem}"
            )
        return DayRecord(
            work_date=_stored_date(row["work_date"], "work date"),
            special_day=row["special_day"],
            start_minute=row["start_minute"],
            end_minute=row["end_minute"],
            break_duration_minutes=row["break_duration_minutes"],
            breaks=breaks,
            expected_work_minutes=row["expected_work_minutes"],
            expected_minutes_overridden=bool(row["expected_minutes_overridden"]),
            revision=row["revision"],
            daily_overtime_minutes=result["daily_overtime_minutes"] if result else None,
            running_balance_minutes=result["running_balance_minutes"] if result else None,
        )

    def _day_row(self, work_date: date, connection=None):
        db = connection or self._connection
        row = db.execute(
            """
            SELECT day.id, day.month_id, day.work_date, day.special_day,
                   day.start_minute, day.end_minute, day.break_duration_minutes,
                   day.expected_work_minutes, day.expected_minutes_overridden,
                   day.revision
            FROM day_entries day
            JOIN months month ON month.id = day.month_id
            WHERE month.dataset_id = ? AND day.work_date = ?
            """,
            (self._dataset_id(db), work_date.isoformat()),
        ).fetchone()
        if row is None:
            raise StorageValidationError(f"No day exists for {work_date.isoformat()}.")
        return row

    def _load_day(self, work_date: date) -> DayRecord:
        with read_transaction(self._connection) as db:
            row = self._day_row(work_date, db)
            result = db.execute(
                """
                SELECT day_entry_id, daily_overtime_minutes, running_balance_minutes
                FROM closed_day_results WHERE day_entry_id = ?
                """,
                (row["id"],),
            ).fetchone()
            breaks = tuple(
                BreakRecord(
                    public_id=pause["public_id"],
                    position=pause["position"],
                    start_minute=pause["start_minute"],
                    end_minute=pause["end_minute"],
                    revision=pause["revision"],
                )
                for pause in db.execute(
                    """
                    SELECT public_id, position, start_minute, end_minute, revision
                    FROM break_periods
                    WHERE day_entry_id = ? ORDER BY position
                    """,
                    (row["id"],),
                ).fetchall()
            )
            return self._day_from_row(row, breaks=breaks, result=result)

    @_repository_operation
    def update_day(
        self,
        work_date: date,
        *,
        expected_revision: int,
        special_day: str | None = None,
        start_minute: int | None = None,
        end_minute: int | None = None,
        break_duration_minutes: int | None = None,
        breaks: tuple[BreakRecord, ...] | None = None,
        expected_work_minutes: int | None = None,
        expected_minutes_overridden: bool | None = None,
        fields: frozenset[str] = frozenset(),
    ) -> DayRecord:
        allowed = {
            "special_day", "start_minute", "end_minute", "break_duration_minutes",
            "breaks", "expected_work_minutes", "expected_minutes_overridden",
        }
        if not fields or not fields <= allowed:
            raise StorageValidationError("The day update must name valid changed fields.")
        if "special_day" in fields:
            special_day_problem = special_day_text_problem(special_day)
            if special_day_problem is not None:
                raise StorageValidationError(special_day_problem)
        for name, value in (("start_minute", start_minute), ("end_minute", end_minute)):
            if name in fields:
                _validate_minute(value)
        if "break_duration_minutes" in fields:
            _validate_minute(break_duration_minutes, allow_1440=True)
        if "expected_work_minutes" in fields:
            _validate_minute(expected_work_minutes, allow_1440=True)

        values = {
            "special_day": special_day,
            "start_minute": start_minute,
            "end_minute": end_minute,
            "break_duration_minutes": break_duration_minutes,
            "expected_work_minutes": expected_work_minutes,
            "expected_minutes_overridden": int(bool(expected_minutes_overridden)),
        }
        with transaction(self._connection) as db:
            row = self._day_row(work_date, db)
            if row["revision"] != expected_revision:
                raise StorageConflict("The day changed since it was loaded.")
            if fields & {"start_minute", "end_minute"}:
                resulting_start = (
                    start_minute if "start_minute" in fields else row["start_minute"]
                )
                resulting_end = (
                    end_minute if "end_minute" in fields else row["end_minute"]
                )
                _validate_work_range(resulting_start, resulting_end)
            if "breaks" in fields:
                final_breaks = breaks or ()
                _validate_break_layout(final_breaks)
                supplied_ids = [pause.public_id for pause in final_breaks if pause.public_id]
                if len(supplied_ids) != len(set(supplied_ids)):
                    raise StorageValidationError("Break public identities must be unique.")
                for public_id in supplied_ids:
                    _validate_uuid4(public_id)
                existing_breaks = {
                    item["public_id"]: item
                    for item in db.execute(
                        """
                        SELECT id, public_id, created_at, revision
                        FROM break_periods WHERE day_entry_id = ?
                        """,
                        (row["id"],),
                    ).fetchall()
                }
                unknown_ids = set(supplied_ids) - set(existing_breaks)
                if unknown_ids:
                    raise StorageValidationError(
                        "A break update referenced an identity not owned by the day."
                    )
                stale_ids = {
                    pause.public_id
                    for pause in final_breaks
                    if pause.public_id
                    and pause.revision != existing_breaks[pause.public_id]["revision"]
                }
                if stale_ids:
                    raise StorageConflict("A break changed since it was loaded.")
                db.execute(
                    "UPDATE day_entries SET break_duration_minutes = NULL WHERE id = ?",
                    (row["id"],),
                )
                now = _utc_text()
                # Remove the old set before rebuilding it. The final layout was
                # validated above, and the surrounding transaction makes this
                # replacement atomic. This avoids overlap triggers observing a
                # mixture of old and new intervals during swaps/reordering.
                db.execute(
                    "DELETE FROM break_periods WHERE day_entry_id = ?", (row["id"],)
                )
                replacement_rows = []
                for position, pause in enumerate(final_breaks):
                    prior = existing_breaks.get(pause.public_id)
                    replacement_rows.append(
                        (
                            prior["id"] if prior is not None else None,
                            (
                                prior["public_id"]
                                if prior is not None
                                else _uuid4()
                            ),
                            row["id"],
                            position,
                            pause.start_minute,
                            pause.end_minute,
                            prior["created_at"] if prior is not None else now,
                            now,
                            prior["revision"] + 1 if prior is not None else 1,
                        )
                    )
                db.executemany(
                    """
                    INSERT INTO break_periods(
                        id, public_id, day_entry_id, position,
                        start_minute, end_minute, created_at, updated_at, revision
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    replacement_rows,
                )
            if "break_duration_minutes" in fields:
                db.execute("DELETE FROM break_periods WHERE day_entry_id = ?", (row["id"],))
            assignments = [f"{name} = ?" for name in fields if name != "breaks"]
            parameters = [values[name] for name in fields if name != "breaks"]
            assignments.extend(
                (
                    "updated_at = ?",
                    "revision = revision + 1",
                    "local_input_revision = local_input_revision + 1",
                )
            )
            parameters.extend((_utc_text(), row["id"], expected_revision))
            cursor = db.execute(
                f"UPDATE day_entries SET {', '.join(assignments)} WHERE id = ? AND revision = ?",
                parameters,
            )
            require_changed(cursor, "The day changed since it was loaded.")
        return self._load_day(work_date)

    @_repository_operation
    def is_month_closed(self, year: int, month: int) -> bool:
        with read_transaction(self._connection) as db:
            row = db.execute(
                """
                SELECT status FROM months
                WHERE dataset_id = ? AND year = ? AND month = ?
                """,
                (self._dataset_id(db), year, month),
            ).fetchone()
            return bool(row and row[0] == "closed")

    @_repository_operation
    def get_carry_over(self, year: int, month: int) -> int:
        with read_transaction(self._connection) as db:
            dataset_id = self._dataset_id(db)
            current = db.execute(
                """
                SELECT opening_balance_minutes FROM months
                WHERE dataset_id = ? AND year = ? AND month = ?
                """,
                (dataset_id, year, month),
            ).fetchone()
            if current:
                return current[0]
            previous_year, previous_month = (
                (year, month - 1) if month > 1 else (year - 1, 12)
            )
            previous = db.execute(
                """
                SELECT closing_balance_minutes FROM months
                WHERE dataset_id = ? AND year = ? AND month = ?
                  AND status = 'closed'
                """,
                (dataset_id, previous_year, previous_month),
            ).fetchone()
            return previous[0] if previous else 0

    @staticmethod
    def _month_close_rows(db, month_id: int):
        return db.execute(
            """
            SELECT id, work_date, special_day, start_minute, end_minute,
                   break_duration_minutes, expected_work_minutes
            FROM day_entries WHERE month_id = ? ORDER BY work_date
            """,
            (month_id,),
        ).fetchall()

    def _unresolved_close_days(self, db, month_id: int):
        return tuple(
            row for row in self._month_close_rows(db, month_id)
            if _unresolved_normal_day(row)
        )

    def _earlier_open_chain_exists(self, db, year: int, month: int) -> bool:
        target = _month_index(year, month)
        return db.execute(
            """
            SELECT 1 FROM months prior_open
            WHERE prior_open.dataset_id = ? AND prior_open.status = 'open'
              AND prior_open.year * 12 + prior_open.month < ?
              AND prior_open.year * 12 + prior_open.month > COALESCE(
                  (
                      SELECT MAX(prior_closed.year * 12 + prior_closed.month)
                      FROM months prior_closed
                      WHERE prior_closed.dataset_id = prior_open.dataset_id
                        AND prior_closed.status = 'closed'
                        AND prior_closed.year * 12 + prior_closed.month < ?
                  ),
                  0
              )
            LIMIT 1
            """,
            (self._dataset_id(db), target, target),
        ).fetchone() is not None

    def _preview_in_transaction(self, db, month_row) -> MonthClosePreview:
        running = month_row["opening_balance_minutes"]
        calculation_rows = self._calculation_rows(db, month_id=month_row["id"])
        running += sum(self._day_overtime_minutes(row) for row in calculation_rows)
        unresolved = tuple(
            _stored_date(row["work_date"], "work date")
            for row in self._unresolved_close_days(db, month_row["id"])
        )
        return MonthClosePreview(
            year=month_row["year"],
            month=month_row["month"],
            opening_balance_minutes=month_row["opening_balance_minutes"],
            closing_balance_minutes=running,
            unresolved_days=unresolved,
        )

    @_repository_operation
    def preview_month_close(self, year: int, month: int) -> MonthClosePreview:
        with read_transaction(self._connection) as db:
            month_row = db.execute(
                """
                SELECT id, year, month, status, opening_balance_minutes
                FROM months WHERE dataset_id = ? AND year = ? AND month = ?
                """,
                (self._dataset_id(db), year, month),
            ).fetchone()
            if month_row is None:
                raise StorageValidationError("The month does not exist.")
            if month_row["status"] == "closed":
                raise ClosedPeriodError("The month is already closed.")
            return self._preview_in_transaction(db, month_row)

    @_repository_operation
    def month_has_carry_discontinuity(self, year: int, month: int) -> bool:
        with read_transaction(self._connection) as db:
            current = db.execute(
                """
                SELECT status, opening_balance_minutes FROM months
                WHERE dataset_id = ? AND year = ? AND month = ?
                """,
                (self._dataset_id(db), year, month),
            ).fetchone()
            if current is None or current["status"] != "closed":
                return False
            previous_year, previous_month = (
                (year, month - 1) if month > 1 else (year - 1, 12)
            )
            previous = db.execute(
                """
                SELECT id, status, closing_balance_minutes
                FROM months WHERE dataset_id = ? AND year = ? AND month = ?
                """,
                (self._dataset_id(db), previous_year, previous_month),
            ).fetchone()
            if previous is None:
                return False
            if previous["status"] == "closed":
                expected = previous["closing_balance_minutes"]
            else:
                expected = self._derived_opening_balance(
                    db, previous_year, previous_month
                ) + sum(
                    self._day_overtime_minutes(row)
                    for row in self._calculation_rows(db, month_id=previous["id"])
                )
            return current["opening_balance_minutes"] != expected

    @_repository_operation
    def reopen_month(self, year: int, month: int, *, expected_revision: int) -> MonthRecord:
        now = _utc_text()
        with transaction(self._connection) as db:
            row = db.execute(
                """
                SELECT id, status, revision FROM months
                WHERE dataset_id = ? AND year = ? AND month = ?
                """,
                (self._dataset_id(db), year, month),
            ).fetchone()
            if row is None:
                raise StorageValidationError("The month does not exist.")
            if row["status"] != "closed":
                raise StorageValidationError("The month is already open.")
            if row["revision"] != expected_revision:
                raise StorageConflict("The month changed since it was loaded.")
            cursor = db.execute(
                """
                UPDATE months SET status = 'open', closing_balance_minutes = NULL,
                    closed_at = NULL, updated_at = ?, revision = revision + 1
                WHERE id = ? AND revision = ?
                """,
                (now, row["id"], expected_revision),
            )
            require_changed(cursor, "The month changed since it was loaded.")
        result = self.load_month(year, month)
        if result is None:
            raise StorageCorrupt("The reopened month disappeared before it was reloaded.")
        return result

    @_repository_operation
    def close_month(
        self,
        year: int,
        month: int,
        *,
        expected_revision: int,
        mark_unresolved_no_data: bool = False,
    ) -> MonthRecord:
        current_date = date.today()
        if date(year, month, 1) > date(current_date.year, current_date.month, 1):
            raise StorageValidationError("A future month cannot be closed.")
        with transaction(self._connection) as db:
            month_row = db.execute(
                """
                SELECT id, year, month, status, opening_balance_minutes, revision
                FROM months WHERE dataset_id = ? AND year = ? AND month = ?
                """,
                (self._dataset_id(db), year, month),
            ).fetchone()
            if month_row is None:
                raise StorageValidationError("The month does not exist.")
            if month_row["status"] == "closed":
                raise ClosedPeriodError("The month is already closed.")
            if month_row["revision"] != expected_revision:
                raise StorageConflict("The month changed since it was loaded.")
            derived_opening = self._derived_opening_balance(db, year, month)
            if derived_opening != month_row["opening_balance_minutes"]:
                raise StorageConflict(
                    "The carry-over changed. Reload the month and review it before closing."
                )
            if self._earlier_open_chain_exists(db, year, month):
                raise StorageValidationError(
                    "An earlier month after the latest closed checkpoint is still open."
                )
            unresolved = self._unresolved_close_days(db, month_row["id"])
            if unresolved and not mark_unresolved_no_data:
                raise StorageValidationError(
                    f"{len(unresolved)} normal day(s) have no work times. "
                    "Fill them or explicitly mark them as No data."
                )
            if unresolved:
                timestamp = _utc_text()
                db.executemany(
                    """
                    UPDATE day_entries SET special_day = ?, updated_at = ?,
                        revision = revision + 1,
                        local_input_revision = local_input_revision + 1
                    WHERE id = ?
                    """,
                    ((NO_DATA_DAY, timestamp, row["id"]) for row in unresolved),
                )
            self._close_month_in_transaction(db, month_row)
        result = self.load_month(year, month)
        if result is None:
            raise StorageCorrupt("The closed month disappeared before it was reloaded.")
        return result

    def _close_month_in_transaction(
        self,
        db: sqlite3.Connection,
        month_row: sqlite3.Row,
        *,
        before_day=None,
        now: str | None = None,
    ) -> tuple[tuple[str, int, int], ...]:
        """Close one loaded open month through the canonical calculation path."""
        db.execute(
            """
            DELETE FROM closed_day_results WHERE day_entry_id IN (
                SELECT id FROM day_entries WHERE month_id = ?
            )
            """,
            (month_row["id"],),
        )
        running = month_row["opening_balance_minutes"]
        calculated = []
        day_rows = db.execute(
            """
            SELECT id, work_date, special_day, start_minute, end_minute,
                   break_duration_minutes, expected_work_minutes
            FROM day_entries WHERE month_id = ? ORDER BY work_date
            """,
            (month_row["id"],),
        ).fetchall()
        interruption_by_day = {
            row["day_entry_id"]: row["interruption_minutes"]
            for row in db.execute(
                """
                SELECT pause.day_entry_id,
                       COALESCE(SUM(pause.end_minute - pause.start_minute), 0)
                           AS interruption_minutes
                FROM break_periods pause
                JOIN day_entries day ON day.id = pause.day_entry_id
                WHERE day.month_id = ?
                GROUP BY pause.day_entry_id
                """,
                (month_row["id"],),
            ).fetchall()
        }
        result_rows = []
        for day in day_rows:
            if before_day is not None:
                before_day()
            overtime = 0
            if day["start_minute"] is not None and day["end_minute"] is not None:
                if day["break_duration_minutes"] is None:
                    interruption = interruption_by_day.get(day["id"], 0)
                else:
                    interruption = day["break_duration_minutes"]
                overtime = (
                    day["end_minute"] - day["start_minute"]
                    - interruption - effective_expected_work_minutes(
                        day["special_day"], day["expected_work_minutes"]
                    )
                )
            running += overtime
            result_rows.append((day["id"], overtime, running))
            calculated.append((day["work_date"], overtime, running))
        db.executemany(
            """
            INSERT INTO closed_day_results(
                day_entry_id, daily_overtime_minutes, running_balance_minutes
            ) VALUES (?, ?, ?)
            """,
            result_rows,
        )
        timestamp = now or _utc_text()
        cursor = db.execute(
            """
            UPDATE months SET status = 'closed', closing_balance_minutes = ?,
                closed_at = ?, updated_at = ?, revision = revision + 1
            WHERE id = ? AND revision = ?
            """,
            (
                running,
                timestamp,
                timestamp,
                month_row["id"],
                month_row["revision"],
            ),
        )
        require_changed(cursor, "The month changed since it was loaded.")
        return tuple(calculated)

    @_repository_operation
    def list_work_schedules(self) -> tuple[WorkSchedulePeriod, ...]:
        with read_transaction(self._connection) as db:
            return tuple(
                WorkSchedulePeriod(
                    public_id=row["public_id"],
                    effective_from=_stored_date(
                        row["effective_from"],
                        "schedule start date",
                    ),
                    effective_to=(
                        _stored_date(row["effective_to"], "schedule end date")
                        if row["effective_to"]
                        else None
                    ),
                    weekday_minutes=tuple(
                        row[column] for column in _SCHEDULE_COLUMNS
                    ),
                    revision=row["revision"],
                )
                for row in db.execute(
                    """
                    SELECT public_id, effective_from, effective_to,
                           monday_minutes, tuesday_minutes, wednesday_minutes,
                           thursday_minutes, friday_minutes, saturday_minutes,
                           sunday_minutes, revision
                    FROM work_schedule_periods
                    WHERE dataset_id = ? ORDER BY effective_from
                    """,
                    (self._dataset_id(db),),
                ).fetchall()
            )

    @_repository_operation
    def replace_work_schedule(
        self,
        *,
        effective_from: date,
        effective_to: date | None,
        weekday_minutes: tuple[int, int, int, int, int, int, int],
        expected_public_id: str,
        expected_revision: int,
    ) -> WorkSchedulePeriod:
        if len(weekday_minutes) != 7:
            raise StorageValidationError("A schedule requires seven weekday values.")
        for value in weekday_minutes:
            _validate_minute(value, allow_1440=True)
        if effective_to and effective_to < effective_from:
            raise StorageValidationError("Schedule end precedes its start.")
        now = _utc_text()
        public_id = _uuid4()
        with transaction(self._connection) as db:
            dataset_id = self._dataset_id(db)
            active = db.execute(
                """
                SELECT public_id, revision FROM work_schedule_periods
                WHERE dataset_id = ? AND effective_from <= ?
                  AND (effective_to IS NULL OR effective_to >= ?)
                ORDER BY effective_from DESC LIMIT 1
                """,
                (
                    dataset_id,
                    effective_from.isoformat(),
                    effective_from.isoformat(),
                ),
            ).fetchone()
            if (
                active is None
                or active["public_id"] != expected_public_id
                or active["revision"] != expected_revision
            ):
                raise StorageConflict(
                    "The work schedule changed since it was loaded. Reload it and try again."
                )
            exact = db.execute(
                f"""
                SELECT id, public_id, effective_to, {', '.join(_SCHEDULE_COLUMNS)}
                FROM work_schedule_periods
                WHERE dataset_id = ? AND effective_from = ?
                """,
                (dataset_id, effective_from.isoformat()),
            ).fetchone()
            following = db.execute(
                """
                SELECT effective_from FROM work_schedule_periods
                WHERE dataset_id = ? AND effective_from > ?
                ORDER BY effective_from LIMIT 1
                """,
                (dataset_id, effective_from.isoformat()),
            ).fetchone()
            derived_end = (
                _stored_date(
                    following["effective_from"],
                    "schedule start date",
                ) - timedelta(days=1)
                if following
                else None
            )
            if effective_to != derived_end:
                expected = derived_end.isoformat() if derived_end else "no end date"
                raise StorageValidationError(
                    f"This schedule must use {expected} to keep schedule coverage continuous."
                )
            previous = db.execute(
                """
                SELECT id FROM work_schedule_periods
                WHERE dataset_id = ? AND effective_from < ?
                  AND (effective_to IS NULL OR effective_to >= ?)
                ORDER BY effective_from DESC LIMIT 1
                """,
                (dataset_id, effective_from.isoformat(), effective_from.isoformat()),
            ).fetchone()
            derived_end_text = derived_end.isoformat() if derived_end else None
            schedule_changed = exact is None or (
                exact["effective_to"] != derived_end_text
                or tuple(exact[column] for column in _SCHEDULE_COLUMNS)
                != weekday_minutes
            )
            if exact:
                public_id = exact["public_id"]
                if schedule_changed:
                    db.execute(
                        f"""
                        UPDATE work_schedule_periods SET effective_to = ?,
                            {', '.join(f'{column} = ?' for column in _SCHEDULE_COLUMNS)},
                            updated_at = ?, revision = revision + 1 WHERE id = ?
                        """,
                        (
                            derived_end_text,
                            *weekday_minutes,
                            now,
                            exact["id"],
                        ),
                    )
            elif previous:
                db.execute(
                    """
                    UPDATE work_schedule_periods SET effective_to = ?, updated_at = ?,
                        revision = revision + 1 WHERE id = ?
                    """,
                    ((effective_from - timedelta(days=1)).isoformat(), now, previous["id"]),
                )
            if not exact:
                db.execute(
                    f"""
                    INSERT INTO work_schedule_periods(
                        public_id, dataset_id, effective_from, effective_to,
                        {', '.join(_SCHEDULE_COLUMNS)}, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (public_id, dataset_id, effective_from.isoformat(),
                     derived_end_text,
                     *weekday_minutes, now, now),
                )
            if schedule_changed:
                weekday_by_sqlite_day = (
                    weekday_minutes[6],
                    weekday_minutes[0],
                    weekday_minutes[1],
                    weekday_minutes[2],
                    weekday_minutes[3],
                    weekday_minutes[4],
                    weekday_minutes[5],
                )
                db.execute(
                    f"""
                    WITH calculated AS (
                        SELECT day.id,
                               day.expected_work_minutes AS current_minutes,
                               CASE CAST(strftime('%w', day.work_date) AS INTEGER)
                                   {' '.join(f'WHEN {day} THEN ?' for day in range(7))}
                               END AS new_minutes
                        FROM day_entries day
                        JOIN months month ON month.id = day.month_id
                        WHERE month.dataset_id = ? AND month.status = 'open'
                          AND day.expected_minutes_overridden = 0
                          AND day.work_date BETWEEN ? AND COALESCE(?, '9999-12-31')
                    )
                    UPDATE day_entries
                    SET expected_work_minutes = (
                            SELECT new_minutes FROM calculated
                            WHERE calculated.id = day_entries.id
                        ),
                        updated_at = ?, revision = revision + 1
                    WHERE id IN (
                        SELECT id FROM calculated
                        WHERE new_minutes != current_minutes
                    )
                    """,
                    (
                        *weekday_by_sqlite_day,
                        dataset_id,
                        effective_from.isoformat(),
                        derived_end_text,
                        now,
                    ),
                )
        result = next(
            (
                item
                for item in self.list_work_schedules()
                if item.public_id == public_id
            ),
            None,
        )
        if result is None:
            raise StorageCorrupt(
                "The updated work schedule disappeared before it was reloaded."
            )
        return result

    @_repository_operation
    def set_day_work_limit(
        self, work_date: date, minutes: int, *, expected_revision: int
    ) -> DayRecord:
        return self.update_day(
            work_date,
            expected_revision=expected_revision,
            expected_work_minutes=minutes,
            expected_minutes_overridden=True,
            fields=frozenset(("expected_work_minutes", "expected_minutes_overridden")),
        )

    @_repository_operation
    def start_workday(self, work_date: date, minute: int, now: datetime) -> DayRecord:
        _validate_minute(minute)
        _require_aware_datetime(now)
        self.get_or_create_month(work_date.year, work_date.month)
        with transaction(self._connection) as db:
            day = self._day_row(work_date, db)
            if day["start_minute"] is not None:
                raise StorageConflict("The workday already has a start time.")
            timestamp = _utc_text(now)
            db.execute(
                """
                UPDATE day_entries SET start_minute = ?, end_minute = NULL,
                    updated_at = ?, revision = revision + 1,
                    local_input_revision = local_input_revision + 1 WHERE id = ?
                """,
                (minute, timestamp, day["id"]),
            )
        return self._load_day(work_date)

    def _running_day(self, work_date: date, db):
        row = self._day_row(work_date, db)
        if row["start_minute"] is None or row["end_minute"] is not None:
            raise StorageConflict(
                "The workday must have a start and no end time for this action."
            )
        return row

    @_repository_operation
    def start_pause(
        self,
        work_date: date,
        minute: int,
        now: datetime,
        *,
        replace_duration: bool = False,
    ) -> DayRecord:
        _validate_minute(minute)
        _require_aware_datetime(now)
        with transaction(self._connection) as db:
            day = self._running_day(work_date, db)
            if db.execute(
                "SELECT 1 FROM break_periods WHERE day_entry_id = ? AND end_minute IS NULL",
                (day["id"],),
            ).fetchone():
                raise StorageConflict("The workday is already paused.")
            if (
                day["break_duration_minutes"] not in (None, 0)
                and replace_duration is not True
            ):
                raise StorageConflict(
                    "The interruption is stored as a duration. Explicit "
                    "replacement confirmation is required before recording "
                    "pause periods."
                )
            timestamp = _utc_text(now)
            db.execute(
                """
                UPDATE day_entries SET break_duration_minutes = NULL,
                    updated_at = ?, revision = revision + 1,
                    local_input_revision = local_input_revision + 1
                WHERE id = ?
                """,
                (timestamp, day["id"]),
            )
            position = db.execute(
                "SELECT COALESCE(MAX(position) + 1, 0) FROM break_periods WHERE day_entry_id = ?",
                (day["id"],),
            ).fetchone()[0]
            db.execute(
                """
                INSERT INTO break_periods(
                    public_id, day_entry_id, position, start_minute, end_minute,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, NULL, ?, ?)
                """,
                (_uuid4(), day["id"], position, minute, timestamp, timestamp),
            )
        return self._load_day(work_date)

    @_repository_operation
    def resume_workday(self, work_date: date, minute: int, now: datetime) -> DayRecord:
        _validate_minute(minute)
        _require_aware_datetime(now)
        with transaction(self._connection) as db:
            day = self._running_day(work_date, db)
            pause = db.execute(
                """
                SELECT id, start_minute FROM break_periods
                WHERE day_entry_id = ? AND end_minute IS NULL
                """,
                (day["id"],),
            ).fetchone()
            if pause is None:
                raise StorageConflict("The workday is not paused.")
            timestamp = _utc_text(now)
            if minute <= pause["start_minute"]:
                db.execute("DELETE FROM break_periods WHERE id = ?", (pause["id"],))
            else:
                db.execute(
                    "UPDATE break_periods SET end_minute = ?, updated_at = ?, revision = revision + 1 WHERE id = ?",
                    (minute, timestamp, pause["id"]),
                )
            db.execute(
                """
                UPDATE day_entries SET updated_at = ?, revision = revision + 1,
                    local_input_revision = local_input_revision + 1
                WHERE id = ?
                """,
                (timestamp, day["id"]),
            )
        return self._load_day(work_date)

    @_repository_operation
    def stop_workday(self, work_date: date, minute: int, now: datetime) -> DayRecord:
        _validate_minute(minute)
        _require_aware_datetime(now)
        with transaction(self._connection) as db:
            day = self._running_day(work_date, db)
            _validate_work_range(day["start_minute"], minute)
            timestamp = _utc_text(now)
            pause = db.execute(
                """
                SELECT id, start_minute FROM break_periods
                WHERE day_entry_id = ? AND end_minute IS NULL
                """,
                (day["id"],),
            ).fetchone()
            if pause:
                if minute <= pause["start_minute"]:
                    db.execute("DELETE FROM break_periods WHERE id = ?", (pause["id"],))
                else:
                    db.execute(
                        "UPDATE break_periods SET end_minute = ?, updated_at = ?, revision = revision + 1 WHERE id = ?",
                        (minute, timestamp, pause["id"]),
                    )
            db.execute(
                """
                UPDATE day_entries SET end_minute = ?, updated_at = ?,
                    revision = revision + 1,
                    local_input_revision = local_input_revision + 1
                WHERE id = ?
                """,
                (minute, timestamp, day["id"]),
            )
        return self._load_day(work_date)

    @_repository_operation
    def backup_to(
        self,
        destination: str | Path,
        *,
        overwrite: bool = False,
        progress=None,
        cancelled=None,
    ) -> None:
        from znactime.storage.legacy_csv_import import (
            _cancel_if_requested,
            _report_progress,
        )

        _cancel_if_requested(cancelled)
        target = Path(destination)
        protected_paths = sqlite_protected_paths(self.path)
        reject_protected_destination(target, protected_paths)
        if target.exists() and not overwrite:
            raise StorageConflict("The backup destination already exists.")
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        os.close(descriptor)
        Path(temporary_name).unlink()
        backup = None
        succeeded = False

        def report_backup(_status, remaining, total):
            _cancel_if_requested(cancelled)
            _report_progress(
                progress,
                "Backing up database",
                total - remaining,
                total,
            )

        try:
            backup = create_database(temporary_name)
            self._connection.backup(
                backup,
                pages=128,
                progress=report_backup,
                sleep=0.05,
            )
            _cancel_if_requested(cancelled)
            _report_progress(progress, "Validating database backup", 0, 0)
            backup.set_progress_handler(
                lambda: int(bool(cancelled and cancelled())),
                1_000,
            )
            if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise StorageValidationError("The database backup failed integrity validation.")
            if backup.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise StorageValidationError("The database backup has invalid relationships.")
            backup.set_progress_handler(None, 0)
            backup.close()
            backup = None
            try:
                publish_staged_file(
                    temporary_name,
                    target,
                    overwrite=overwrite,
                    protected_paths=protected_paths,
                )
            except FileExistsError as error:
                raise StorageConflict(
                    "The backup destination appeared before backup completed."
                ) from error
            succeeded = True
        except sqlite3.Error as error:
            _cancel_if_requested(cancelled)
            raise translate_error(error) from error
        finally:
            if backup is not None:
                backup.close()
            if not succeeded:
                try:
                    Path(temporary_name).unlink()
                except OSError:
                    pass

    @_repository_operation
    def merge_legacy(
        self,
        preflight,
        *,
        progress=None,
        cancelled=None,
        log_database_path=None,
    ):
        from znactime.storage.legacy_import_log import write_legacy_import_log
        from znactime.storage.sqlite.legacy_import import merge_preflight

        generated_log = None

        def create_log(result):
            nonlocal generated_log
            log_path = write_legacy_import_log(
                log_database_path or self.path,
                preflight,
                result,
            )
            generated_log = log_path
            return replace(result, log_path=log_path)

        try:
            result = merge_preflight(
                self,
                preflight,
                progress=progress,
                cancelled=cancelled,
                before_commit=create_log,
            )
        except Exception:
            if generated_log is not None:
                try:
                    generated_log.unlink()
                except OSError:
                    pass
            raise
        if not result.already_imported:
            self._last_import_log_path = result.log_path
        return result

    @property
    def last_import_log_path(self) -> Path | None:
        return self._last_import_log_path

    @_repository_operation
    def close(self) -> None:
        self._connection.close()
