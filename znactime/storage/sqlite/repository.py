from __future__ import annotations

import calendar
import os
import sqlite3
import tempfile
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from znactime.config import VERSION
from znactime.core.constants import NORMAL_DAY
from znactime.core.models import (
    BreakRecord,
    DayRecord,
    MonthRecord,
    WorkSchedulePeriod,
)
from znactime.storage.errors import (
    ClosedPeriodError,
    StorageConflict,
    StorageCorrupt,
    StorageValidationError,
    StorageVersionUnsupported,
)
from znactime.storage.atomic_file import (
    publish_staged_file,
    reject_protected_destination,
    sqlite_protected_paths,
)
from znactime.storage.sqlite.connection import (
    connect_database,
    read_transaction,
    require_changed,
    transaction,
    translate_error,
)
from znactime.storage.sqlite.migrations import MIGRATIONS
from znactime.storage.sqlite.schema import SCHEMA_SQL, SCHEMA_VERSION


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
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _uuid4() -> str:
    return str(uuid.uuid4())


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
        self._connection = connect_database(self.path)
        try:
            self._upgrade_schema()
            self._verify_version()
        except Exception:
            self._connection.close()
            raise

    @classmethod
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
        connection = connect_database(target)
        try:
            if connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' LIMIT 1"
            ).fetchone():
                raise StorageConflict("The target database is not empty.")
            connection.executescript(SCHEMA_SQL)
            now = _utc_text()
            with transaction(connection):
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at, app_version) VALUES (?, ?, ?)",
                    (SCHEMA_VERSION, now, VERSION),
                )
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                dataset_id = connection.execute(
                    "INSERT INTO datasets(public_id, created_at) VALUES (?, ?)",
                    (dataset_public_id or _uuid4(), now),
                ).lastrowid
                values = (default_workday_minutes,) * 7
                connection.execute(
                    f"""
                    INSERT INTO work_schedule_periods(
                        public_id, dataset_id, effective_from, effective_to,
                        {', '.join(_SCHEDULE_COLUMNS)}, created_at, updated_at
                    ) VALUES (?, ?, '0001-01-01', NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (_uuid4(), dataset_id, *values, now, now),
                )
            checks = connection.execute("PRAGMA integrity_check").fetchone()[0]
            if checks != "ok":
                raise StorageValidationError("The created database failed integrity validation.")
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

    def _verify_version(self):
        try:
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            migration = self._connection.execute(
                "SELECT MAX(version) FROM schema_migrations"
            ).fetchone()[0]
            if self._connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise StorageCorrupt("The time database failed its startup integrity check.")
            if self._connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise StorageCorrupt("The time database contains invalid relationships.")
            self._dataset_id()
        except sqlite3.Error as error:
            raise translate_error(error) from error
        if version != SCHEMA_VERSION or migration != SCHEMA_VERSION:
            raise StorageVersionUnsupported(
                f"Database schema {version!r}/{migration!r} is not supported."
            )

    def _upgrade_schema(self):
        try:
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            migration = self._connection.execute(
                "SELECT MAX(version) FROM schema_migrations"
            ).fetchone()[0]
        except sqlite3.Error as error:
            raise translate_error(error) from error

        if version == SCHEMA_VERSION and migration == SCHEMA_VERSION:
            return
        if version != migration or version not in MIGRATIONS:
            return

        while version < SCHEMA_VERSION:
            migration_sql = MIGRATIONS.get(version)
            if migration_sql is None:
                return
            self._validate_migration_source(version)
            with transaction(self._connection) as db:
                for statement in _migration_statements(migration_sql):
                    db.execute(statement)
                version += 1
                db.execute(
                    "INSERT INTO schema_migrations(version, applied_at, app_version) "
                    "VALUES (?, ?, ?)",
                    (version, _utc_text(), VERSION),
                )
                db.execute(f"PRAGMA user_version = {version}")

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
        db = connection or self._connection
        rows = db.execute("SELECT id FROM datasets ORDER BY id").fetchall()
        if len(rows) != 1:
            raise StorageValidationError("The database must contain exactly one local dataset.")
        return rows[0][0]

    def _expected_minutes(self, work_date: date, connection=None) -> int:
        db = connection or self._connection
        row = db.execute(
            f"""
            SELECT {', '.join(_SCHEDULE_COLUMNS)}
            FROM work_schedule_periods
            WHERE dataset_id = ? AND effective_from <= ?
              AND (effective_to IS NULL OR effective_to >= ?)
            ORDER BY effective_from DESC LIMIT 1
            """,
            (self._dataset_id(db), work_date.isoformat(), work_date.isoformat()),
        ).fetchone()
        if row is None:
            raise StorageValidationError(f"No work schedule applies to {work_date.isoformat()}.")
        return row[work_date.weekday()]

    def get_or_create_month(self, year: int, month: int) -> MonthRecord:
        try:
            date(year, month, 1)
        except ValueError as error:
            raise StorageValidationError("Invalid calendar month.") from error
        existing = self.load_month(year, month)
        if existing is not None:
            return existing
        now = _utc_text()
        with transaction(self._connection) as db:
            dataset_id = self._dataset_id(db)
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
                        self._expected_minutes(work_date, db),
                        now,
                        now,
                    ),
                )
        result = self.load_month(year, month)
        assert result is not None
        return result

    def load_month(self, year: int, month: int) -> MonthRecord | None:
        with read_transaction(self._connection) as db:
            row = db.execute(
                """
                SELECT id, year, month, status, opening_balance_minutes,
                       closing_balance_minutes, revision
                FROM months WHERE dataset_id = ? AND year = ? AND month = ?
                """,
                (self._dataset_id(db), year, month),
            ).fetchone()
            if row is None:
                return None
            days = tuple(
                self._day_from_row(day)
                for day in db.execute(
                    "SELECT * FROM day_entries WHERE month_id = ? ORDER BY work_date",
                    (row["id"],),
                ).fetchall()
            )
            return MonthRecord(
                year=row["year"],
                month=row["month"],
                status=row["status"],
                opening_balance_minutes=row["opening_balance_minutes"],
                closing_balance_minutes=row["closing_balance_minutes"],
                revision=row["revision"],
                days=days,
            )

    def list_months(self, year: int | None = None) -> tuple[MonthRecord, ...]:
        if year is None:
            rows = self._connection.execute(
                "SELECT year, month FROM months WHERE dataset_id = ? ORDER BY year, month",
                (self._dataset_id(),),
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT year, month FROM months WHERE dataset_id = ? AND year = ? ORDER BY month",
                (self._dataset_id(), year),
            ).fetchall()
        return tuple(self.load_month(row["year"], row["month"]) for row in rows)

    def _day_from_row(self, row) -> DayRecord:
        result = self._connection.execute(
            "SELECT * FROM closed_day_results WHERE day_entry_id = ?",
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
            for pause in self._connection.execute(
                "SELECT * FROM break_periods WHERE day_entry_id = ? ORDER BY position",
                (row["id"],),
            ).fetchall()
        )
        return DayRecord(
            work_date=date.fromisoformat(row["work_date"]),
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
            SELECT day.* FROM day_entries day
            JOIN months month ON month.id = day.month_id
            WHERE month.dataset_id = ? AND day.work_date = ?
            """,
            (self._dataset_id(db), work_date.isoformat()),
        ).fetchone()
        if row is None:
            raise StorageValidationError(f"No day exists for {work_date.isoformat()}.")
        return row

    def _load_day(self, work_date: date) -> DayRecord:
        return self._day_from_row(self._day_row(work_date))

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
        if "special_day" in fields and not special_day:
            raise StorageValidationError("Special day text cannot be empty.")
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
            if "breaks" in fields:
                supplied_ids = [pause.public_id for pause in breaks or () if pause.public_id]
                if len(supplied_ids) != len(set(supplied_ids)):
                    raise StorageValidationError("Break public identities must be unique.")
                for public_id in supplied_ids:
                    _validate_uuid4(public_id)
                existing_breaks = {
                    item["public_id"]: item
                    for item in db.execute(
                        "SELECT * FROM break_periods WHERE day_entry_id = ?",
                        (row["id"],),
                    ).fetchall()
                }
                unknown_ids = set(supplied_ids) - set(existing_breaks)
                if unknown_ids:
                    raise StorageValidationError(
                        "A break update referenced an identity not owned by the day."
                    )
                db.execute(
                    "UPDATE day_entries SET break_duration_minutes = NULL WHERE id = ?",
                    (row["id"],),
                )
                now = _utc_text()
                retained_ids = set(supplied_ids)
                if retained_ids:
                    placeholders = ", ".join("?" for _item in retained_ids)
                    db.execute(
                        f"DELETE FROM break_periods WHERE day_entry_id = ? "
                        f"AND public_id NOT IN ({placeholders})",
                        (row["id"], *sorted(retained_ids)),
                    )
                    db.execute(
                        f"UPDATE break_periods SET position = position + 10000 "
                        f"WHERE day_entry_id = ? AND public_id IN ({placeholders})",
                        (row["id"], *sorted(retained_ids)),
                    )
                else:
                    db.execute(
                        "DELETE FROM break_periods WHERE day_entry_id = ?", (row["id"],)
                    )
                for position, pause in enumerate(breaks or ()):
                    _validate_minute(pause.start_minute)
                    _validate_minute(pause.end_minute)
                    if pause.public_id:
                        db.execute(
                            """
                            UPDATE break_periods SET position = ?, start_minute = ?,
                                end_minute = ?, updated_at = ?, revision = revision + 1
                            WHERE public_id = ? AND day_entry_id = ?
                            """,
                            (
                                position,
                                pause.start_minute,
                                pause.end_minute,
                                now,
                                pause.public_id,
                                row["id"],
                            ),
                        )
                    else:
                        db.execute(
                            """
                            INSERT INTO break_periods(
                                public_id, day_entry_id, position, start_minute, end_minute,
                                created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                _uuid4(), row["id"], position,
                                pause.start_minute, pause.end_minute, now, now,
                            ),
                        )
            if "break_duration_minutes" in fields:
                db.execute("DELETE FROM break_periods WHERE day_entry_id = ?", (row["id"],))
            assignments = [f"{name} = ?" for name in fields if name != "breaks"]
            parameters = [values[name] for name in fields if name != "breaks"]
            assignments.extend(("updated_at = ?", "revision = revision + 1"))
            parameters.extend((_utc_text(), row["id"], expected_revision))
            cursor = db.execute(
                f"UPDATE day_entries SET {', '.join(assignments)} WHERE id = ? AND revision = ?",
                parameters,
            )
            require_changed(cursor, "The day changed since it was loaded.")
        return self._load_day(work_date)

    def is_month_closed(self, year: int, month: int) -> bool:
        row = self._connection.execute(
            "SELECT status FROM months WHERE dataset_id = ? AND year = ? AND month = ?",
            (self._dataset_id(), year, month),
        ).fetchone()
        return bool(row and row[0] == "closed")

    def get_carry_over(self, year: int, month: int) -> int:
        current = self._connection.execute(
            "SELECT opening_balance_minutes FROM months WHERE dataset_id = ? AND year = ? AND month = ?",
            (self._dataset_id(), year, month),
        ).fetchone()
        if current:
            return current[0]
        previous_year, previous_month = (year, month - 1) if month > 1 else (year - 1, 12)
        previous = self._connection.execute(
            """
            SELECT closing_balance_minutes FROM months
            WHERE dataset_id = ? AND year = ? AND month = ? AND status = 'closed'
            """,
            (self._dataset_id(), previous_year, previous_month),
        ).fetchone()
        return previous[0] if previous else 0

    def close_month(self, year: int, month: int, *, expected_revision: int) -> MonthRecord:
        with transaction(self._connection) as db:
            month_row = db.execute(
                "SELECT * FROM months WHERE dataset_id = ? AND year = ? AND month = ?",
                (self._dataset_id(db), year, month),
            ).fetchone()
            if month_row is None:
                raise StorageValidationError("The month does not exist.")
            if month_row["status"] == "closed":
                raise ClosedPeriodError("The month is already closed.")
            if month_row["revision"] != expected_revision:
                raise StorageConflict("The month changed since it was loaded.")
            db.execute(
                """
                DELETE FROM closed_day_results WHERE day_entry_id IN (
                    SELECT id FROM day_entries WHERE month_id = ?
                )
                """,
                (month_row["id"],),
            )
            running = month_row["opening_balance_minutes"]
            day_rows = db.execute(
                "SELECT * FROM day_entries WHERE month_id = ? ORDER BY work_date",
                (month_row["id"],),
            ).fetchall()
            for day in day_rows:
                overtime = 0
                if day["start_minute"] is not None and day["end_minute"] is not None:
                    if day["break_duration_minutes"] is None:
                        interruption = db.execute(
                            """
                            SELECT COALESCE(SUM(end_minute - start_minute), 0)
                            FROM break_periods WHERE day_entry_id = ?
                            """,
                            (day["id"],),
                        ).fetchone()[0]
                    else:
                        interruption = day["break_duration_minutes"]
                    overtime = (
                        day["end_minute"] - day["start_minute"]
                        - interruption - day["expected_work_minutes"]
                    )
                running += overtime
                db.execute(
                    """
                    INSERT INTO closed_day_results(
                        day_entry_id, daily_overtime_minutes, running_balance_minutes
                    ) VALUES (?, ?, ?)
                    """,
                    (day["id"], overtime, running),
                )
            now = _utc_text()
            cursor = db.execute(
                """
                UPDATE months SET status = 'closed', closing_balance_minutes = ?,
                    closed_at = ?, updated_at = ?, revision = revision + 1
                WHERE id = ? AND revision = ?
                """,
                (running, now, now, month_row["id"], expected_revision),
            )
            require_changed(cursor, "The month changed since it was loaded.")
        result = self.load_month(year, month)
        assert result is not None
        return result

    def list_work_schedules(self) -> tuple[WorkSchedulePeriod, ...]:
        return tuple(
            WorkSchedulePeriod(
                public_id=row["public_id"],
                effective_from=date.fromisoformat(row["effective_from"]),
                effective_to=date.fromisoformat(row["effective_to"]) if row["effective_to"] else None,
                weekday_minutes=tuple(row[column] for column in _SCHEDULE_COLUMNS),
                revision=row["revision"],
            )
            for row in self._connection.execute(
                "SELECT * FROM work_schedule_periods WHERE dataset_id = ? ORDER BY effective_from",
                (self._dataset_id(),),
            ).fetchall()
        )

    def replace_work_schedule(
        self,
        *,
        effective_from: date,
        effective_to: date | None,
        weekday_minutes: tuple[int, int, int, int, int, int, int],
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
            exact = db.execute(
                "SELECT * FROM work_schedule_periods WHERE dataset_id = ? AND effective_from = ?",
                (dataset_id, effective_from.isoformat()),
            ).fetchone()
            following = db.execute(
                """
                SELECT * FROM work_schedule_periods
                WHERE dataset_id = ? AND effective_from > ?
                ORDER BY effective_from LIMIT 1
                """,
                (dataset_id, effective_from.isoformat()),
            ).fetchone()
            derived_end = (
                date.fromisoformat(following["effective_from"]) - timedelta(days=1)
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
                SELECT * FROM work_schedule_periods
                WHERE dataset_id = ? AND effective_from < ?
                  AND (effective_to IS NULL OR effective_to >= ?)
                ORDER BY effective_from DESC LIMIT 1
                """,
                (dataset_id, effective_from.isoformat(), effective_from.isoformat()),
            ).fetchone()
            if exact:
                public_id = exact["public_id"]
                db.execute(
                    f"""
                    UPDATE work_schedule_periods SET effective_to = ?,
                        {', '.join(f'{column} = ?' for column in _SCHEDULE_COLUMNS)},
                        updated_at = ?, revision = revision + 1 WHERE id = ?
                    """,
                    (
                        derived_end.isoformat() if derived_end else None,
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
                     derived_end.isoformat() if derived_end else None,
                     *weekday_minutes, now, now),
                )
            affected = db.execute(
                """
                SELECT day.id, day.work_date FROM day_entries day
                JOIN months month ON month.id = day.month_id
                WHERE month.dataset_id = ? AND month.status = 'open'
                  AND day.expected_minutes_overridden = 0 AND day.work_date >= ?
                """,
                (dataset_id, effective_from.isoformat()),
            ).fetchall()
            for day in affected:
                day_date = date.fromisoformat(day["work_date"])
                db.execute(
                    """
                    UPDATE day_entries SET expected_work_minutes = ?, updated_at = ?,
                        revision = revision + 1 WHERE id = ?
                    """,
                    (self._expected_minutes(day_date, db), now, day["id"]),
                )
        return next(item for item in self.list_work_schedules() if item.public_id == public_id)

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

    def start_workday(self, work_date: date, minute: int, now: datetime) -> DayRecord:
        _validate_minute(minute)
        self.get_or_create_month(work_date.year, work_date.month)
        with transaction(self._connection) as db:
            day = self._day_row(work_date, db)
            if day["start_minute"] is not None:
                raise StorageConflict("The workday already has a start time.")
            timestamp = _utc_text(now)
            db.execute(
                """
                UPDATE day_entries SET start_minute = ?, end_minute = NULL,
                    updated_at = ?, revision = revision + 1 WHERE id = ?
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

    def start_pause(
        self,
        work_date: date,
        minute: int,
        now: datetime,
        *,
        replace_duration: bool = False,
    ) -> DayRecord:
        _validate_minute(minute)
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
                "UPDATE day_entries SET break_duration_minutes = NULL, updated_at = ?, revision = revision + 1 WHERE id = ?",
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

    def resume_workday(self, work_date: date, minute: int, now: datetime) -> DayRecord:
        _validate_minute(minute)
        with transaction(self._connection) as db:
            day = self._running_day(work_date, db)
            pause = db.execute(
                "SELECT * FROM break_periods WHERE day_entry_id = ? AND end_minute IS NULL",
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
                "UPDATE day_entries SET updated_at = ?, revision = revision + 1 WHERE id = ?",
                (timestamp, day["id"]),
            )
        return self._load_day(work_date)

    def stop_workday(self, work_date: date, minute: int, now: datetime) -> DayRecord:
        _validate_minute(minute)
        with transaction(self._connection) as db:
            day = self._running_day(work_date, db)
            timestamp = _utc_text(now)
            pause = db.execute(
                "SELECT * FROM break_periods WHERE day_entry_id = ? AND end_minute IS NULL",
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
                "UPDATE day_entries SET end_minute = ?, updated_at = ?, revision = revision + 1 WHERE id = ?",
                (minute, timestamp, day["id"]),
            )
        return self._load_day(work_date)

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
            backup = connect_database(temporary_name)
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

    def merge_legacy(self, preflight, *, progress=None, cancelled=None):
        from znactime.storage.sqlite.legacy_import import merge_preflight

        return merge_preflight(
            self,
            preflight,
            progress=progress,
            cancelled=cancelled,
        )

    def close(self) -> None:
        self._connection.close()
