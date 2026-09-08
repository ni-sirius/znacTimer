import os
import csv
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier, Lock
from unittest.mock import patch

from znactime.core.models import BreakRecord
from znactime.core.validation import MAX_SPECIAL_DAY_LENGTH
from znactime.storage.atomic_file import sqlite_protected_paths
from znactime.storage.errors import (
    ClosedPeriodError,
    ExportError,
    StorageConflict,
    StorageCorrupt,
    StorageError,
    StorageLocked,
    StorageUnavailable,
    StorageValidationError,
)
from znactime.storage.csv_export import export_month
from znactime.storage.csv_format import spreadsheet_safe_text
from znactime.storage.legacy_csv_import import preflight_legacy_data
from znactime.storage.legacy_csv_import import LegacyImportCancelled
from znactime.storage.sqlite.repository import SQLiteRepository
from znactime.storage.sqlite.schema import SCHEMA_VERSION


class SQLiteRepositoryTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "znactime.db"
        self.repository = SQLiteRepository.create(self.path)
        self.sql = sqlite3.connect(self.path, isolation_level=None)
        self.sql.execute("PRAGMA foreign_keys = ON")

    def tearDown(self):
        self.sql.close()
        self.repository.close()
        self.temporary.cleanup()

    def _replace_schedule(
        self,
        *,
        effective_from,
        effective_to,
        weekday_minutes,
        repository=None,
    ):
        repository = repository or self.repository
        active = next(
            item
            for item in repository.list_work_schedules()
            if item.effective_from <= effective_from
            and (item.effective_to is None or item.effective_to >= effective_from)
        )
        return repository.replace_work_schedule(
            effective_from=effective_from,
            effective_to=effective_to,
            weekday_minutes=weekday_minutes,
            expected_public_id=active.public_id,
            expected_revision=active.revision,
        )

    def test_opening_a_missing_repository_does_not_create_a_blank_file(self):
        missing = Path(self.temporary.name) / "missing.db"

        with self.assertRaises(StorageUnavailable):
            SQLiteRepository(missing)

        self.assertFalse(missing.exists())

    def test_explicit_create_is_the_only_repository_path_that_creates_a_file(self):
        created_path = Path(self.temporary.name) / "explicit.db"

        created = SQLiteRepository.create(created_path)
        try:
            self.assertTrue(created_path.is_file())
            self.assertEqual(created.list_months(), ())
        finally:
            created.close()

    def test_schema_creation_failure_rolls_back_all_ddl(self):
        failed_path = Path(self.temporary.name) / "failed-create.db"
        broken_schema = """
        CREATE TABLE should_roll_back (id INTEGER PRIMARY KEY) STRICT;
        THIS IS NOT VALID SQL;
        """

        with patch(
            "znactime.storage.sqlite.repository.SCHEMA_SQL",
            broken_schema,
        ):
            with self.assertRaises(StorageError):
                SQLiteRepository.create(failed_path)

        self.assertTrue(failed_path.is_file())
        failed = sqlite3.connect(failed_path)
        try:
            objects = failed.execute(
                "SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            ).fetchall()
            self.assertEqual(objects, [])
        finally:
            failed.close()

    def test_create_and_calendar_month_round_trip(self):
        month = self.repository.get_or_create_month(2024, 2)

        self.assertEqual(len(month.days), 29)
        self.assertEqual(month.days[0].work_date, date(2024, 2, 1))
        self.assertEqual(month.days[-1].work_date, date(2024, 2, 29))
        self.assertEqual(month.days[0].expected_work_minutes, 480)
        self.assertEqual(
            self.repository.list_work_schedules()[0].weekday_minutes,
            (480, 480, 480, 480, 480, 0, 0),
        )
        self.assertEqual(month.days[2].expected_work_minutes, 0)

    def test_concurrent_month_creation_converges_after_both_observe_missing(self):
        original_load = SQLiteRepository.load_month
        first_loads: set[int] = set()
        first_loads_lock = Lock()
        both_observed_missing = Barrier(2)

        def synchronized_load(repository, year, month):
            result = original_load(repository, year, month)
            with first_loads_lock:
                first_for_repository = id(repository) not in first_loads
                first_loads.add(id(repository))
            if first_for_repository:
                self.assertIsNone(result)
                both_observed_missing.wait(timeout=5)
            return result

        def create_from_one_connection():
            repository = SQLiteRepository(self.path)
            try:
                return repository.get_or_create_month(2024, 8)
            finally:
                repository.close()

        with patch.object(SQLiteRepository, "load_month", new=synchronized_load):
            with ThreadPoolExecutor(max_workers=2) as executor:
                months = tuple(
                    executor.map(lambda _item: create_from_one_connection(), range(2))
                )

        self.assertEqual([(item.year, item.month) for item in months], [(2024, 8)] * 2)
        self.assertEqual(
            self.sql.execute(
                "SELECT COUNT(*) FROM months WHERE year = 2024 AND month = 8"
            ).fetchone()[0],
            1,
        )
        self.assertEqual(
            self.sql.execute(
                """
                SELECT COUNT(*) FROM day_entries day
                JOIN months month ON month.id = day.month_id
                WHERE month.year = 2024 AND month.month = 8
                """
            ).fetchone()[0],
            31,
        )

    def test_month_reads_use_fixed_count_bulk_queries_in_one_snapshot(self):
        self.repository.get_or_create_month(2024, 2)
        self.repository.get_or_create_month(2024, 3)

        for load, expected_months in (
            (lambda: (self.repository.load_month(2024, 2),), 1),
            (lambda: self.repository.list_months(2024), 2),
        ):
            statements = []
            self.repository._connection.set_trace_callback(statements.append)
            try:
                records = load()
            finally:
                self.repository._connection.set_trace_callback(None)

            selects = [
                statement
                for statement in statements
                if statement.lstrip().upper().startswith("SELECT")
            ]
            self.assertEqual(len(records), expected_months)
            self.assertEqual(len(selects), 4)
            self.assertFalse(any("FROM datasets" in item for item in selects))
            self.assertTrue(any(item == "BEGIN" for item in statements))
            self.assertTrue(any(item == "COMMIT" for item in statements))

    def test_single_day_reload_uses_one_read_transaction(self):
        work_date = date(2024, 6, 3)
        self.repository.get_or_create_month(2024, 6)
        statements = []
        self.repository._connection.set_trace_callback(statements.append)
        try:
            loaded = self.repository._load_day(work_date)
        finally:
            self.repository._connection.set_trace_callback(None)

        selects = [
            statement
            for statement in statements
            if statement.lstrip().upper().startswith("SELECT")
        ]
        self.assertEqual(loaded.work_date, work_date)
        self.assertEqual(len(selects), 3)
        self.assertFalse(any("FROM datasets" in item for item in selects))
        self.assertTrue(any(item == "BEGIN" for item in statements))
        self.assertTrue(any(item == "COMMIT" for item in statements))

    def test_public_reads_translate_exclusive_lock_errors(self):
        self.repository.get_or_create_month(2024, 2)
        self.repository._connection.execute("PRAGMA busy_timeout = 1")
        blocker = sqlite3.connect(self.path, isolation_level=None)
        blocker.execute("BEGIN EXCLUSIVE")
        try:
            reads = (
                lambda: self.repository.load_month(2024, 2),
                lambda: self.repository.list_months(),
                lambda: self.repository.is_month_closed(2024, 2),
                lambda: self.repository.get_carry_over(2024, 2),
                lambda: self.repository.list_work_schedules(),
            )
            for read in reads:
                with self.subTest(read=read), self.assertRaises(StorageLocked):
                    read()
        finally:
            blocker.execute("ROLLBACK")
            blocker.close()

    def test_public_reads_translate_closed_connection_errors(self):
        self.repository.get_or_create_month(2024, 2)
        self.repository.close()

        reads = (
            lambda: self.repository.load_month(2024, 2),
            lambda: self.repository.list_months(),
            lambda: self.repository.is_month_closed(2024, 2),
            lambda: self.repository.get_carry_over(2024, 2),
            lambda: self.repository.list_work_schedules(),
        )
        for read in reads:
            with self.subTest(read=read), self.assertRaises(StorageUnavailable):
                read()

    def test_malformed_stored_date_is_exposed_as_storage_corrupt(self):
        self.repository.get_or_create_month(2024, 2)
        self.sql.execute("PRAGMA ignore_check_constraints = ON")
        self.sql.execute("DROP TRIGGER day_date_valid_update")
        self.sql.execute("DROP TRIGGER day_guard_update")
        self.sql.execute(
            "UPDATE day_entries SET work_date = 'not-a-date' WHERE work_date = '2024-02-01'"
        )

        with self.assertRaises(StorageCorrupt):
            self.repository.load_month(2024, 2)

    def test_read_only_and_filesystem_failures_use_domain_errors(self):
        month = self.repository.get_or_create_month(2024, 2)
        day = month.days[0]
        self.repository._connection.execute("PRAGMA query_only = ON")
        try:
            with self.assertRaises(StorageUnavailable):
                self.repository.update_day(
                    day.work_date,
                    expected_revision=day.revision,
                    special_day="Changed",
                    fields=frozenset(("special_day",)),
                )
        finally:
            self.repository._connection.execute("PRAGMA query_only = OFF")

        not_a_directory = Path(self.temporary.name) / "not-a-directory"
        not_a_directory.write_bytes(b"file")
        with self.assertRaises(StorageUnavailable):
            self.repository.backup_to(not_a_directory / "backup.db")
        columns = {
            row[1]
            for row in self.sql.execute("PRAGMA table_info(months)")
        }
        self.assertNotIn("public_id", columns)

    def test_update_uses_expected_revision_and_null_midnight_is_distinct(self):
        day = self.repository.get_or_create_month(2024, 6).days[0]
        changed = self.repository.update_day(
            day.work_date,
            expected_revision=day.revision,
            start_minute=0,
            end_minute=480,
            fields=frozenset(("start_minute", "end_minute")),
        )

        self.assertEqual(changed.start_minute, 0)
        self.assertEqual(changed.end_minute, 480)
        self.assertEqual(changed.revision, day.revision + 1)
        with self.assertRaises(StorageConflict):
            self.repository.update_day(
                day.work_date,
                expected_revision=day.revision,
                special_day="Vacation",
                fields=frozenset(("special_day",)),
            )

    def test_day_update_rejects_end_without_start_and_nonpositive_range(self):
        day = self.repository.get_or_create_month(2024, 6).days[0]

        with self.assertRaisesRegex(StorageValidationError, "requires a start"):
            self.repository.update_day(
                day.work_date,
                expected_revision=day.revision,
                end_minute=600,
                fields=frozenset(("end_minute",)),
            )
        unchanged = self.repository.load_month(2024, 6).days[0]
        self.assertIsNone(unchanged.end_minute)
        self.assertEqual(unchanged.revision, day.revision)

        started = self.repository.update_day(
            day.work_date,
            expected_revision=unchanged.revision,
            start_minute=480,
            fields=frozenset(("start_minute",)),
        )
        for invalid_end in (480, 400):
            with self.subTest(end=invalid_end), self.assertRaisesRegex(
                StorageValidationError,
                "later than start",
            ):
                self.repository.update_day(
                    day.work_date,
                    expected_revision=started.revision,
                    end_minute=invalid_end,
                    fields=frozenset(("end_minute",)),
                )
        preserved = self.repository.load_month(2024, 6).days[0]
        self.assertEqual(preserved.start_minute, 480)
        self.assertIsNone(preserved.end_minute)
        self.assertEqual(preserved.revision, started.revision)

    def test_break_representation_and_overlap_are_enforced(self):
        day = self.repository.get_or_create_month(2024, 6).days[0]
        changed = self.repository.update_day(
            day.work_date,
            expected_revision=day.revision,
            breaks=(BreakRecord("", 0, 720, 750),),
            fields=frozenset(("breaks",)),
        )
        self.assertIsNone(changed.break_duration_minutes)
        self.assertEqual(len(changed.breaks), 1)

        day_id = self.sql.execute(
            "SELECT id FROM day_entries WHERE work_date = ?", (day.work_date.isoformat(),)
        ).fetchone()[0]
        with self.assertRaises(sqlite3.IntegrityError):
            self.sql.execute(
                """
                INSERT INTO break_periods(
                    public_id, day_entry_id, position, start_minute, end_minute,
                    created_at, updated_at
                ) VALUES ('duplicate-test', ?, 1, 730, 760, 'x', 'x')
                """,
                (day_id,),
            )

    def test_break_interval_swap_is_atomic_and_preserves_identities(self):
        day = self.repository.get_or_create_month(2024, 6).days[0]
        original = self.repository.update_day(
            day.work_date,
            expected_revision=day.revision,
            breaks=(
                BreakRecord("", 0, 720, 750),
                BreakRecord("", 1, 900, 930),
            ),
            fields=frozenset(("breaks",)),
        )
        internal_ids = dict(
            self.sql.execute(
                "SELECT public_id, id FROM break_periods WHERE day_entry_id = "
                "(SELECT id FROM day_entries WHERE work_date = ?)",
                (day.work_date.isoformat(),),
            ).fetchall()
        )

        swapped = self.repository.update_day(
            day.work_date,
            expected_revision=original.revision,
            breaks=(
                BreakRecord(
                    original.breaks[0].public_id,
                    0,
                    900,
                    930,
                    original.breaks[0].revision,
                ),
                BreakRecord(
                    original.breaks[1].public_id,
                    1,
                    720,
                    750,
                    original.breaks[1].revision,
                ),
            ),
            fields=frozenset(("breaks",)),
        )

        self.assertEqual(
            [(item.start_minute, item.end_minute) for item in swapped.breaks],
            [(900, 930), (720, 750)],
        )
        self.assertEqual(
            [item.public_id for item in swapped.breaks],
            [item.public_id for item in original.breaks],
        )
        self.assertEqual(
            dict(self.sql.execute("SELECT public_id, id FROM break_periods").fetchall()),
            internal_ids,
        )
        self.assertEqual(
            [item.revision for item in swapped.breaks],
            [item.revision + 1 for item in original.breaks],
        )

    def test_invalid_final_break_layout_is_rejected_without_mutation(self):
        day = self.repository.get_or_create_month(2024, 6).days[0]
        original = self.repository.update_day(
            day.work_date,
            expected_revision=day.revision,
            breaks=(BreakRecord("", 0, 720, 750),),
            fields=frozenset(("breaks",)),
        )

        with self.assertRaisesRegex(StorageValidationError, "cannot overlap"):
            self.repository.update_day(
                day.work_date,
                expected_revision=original.revision,
                breaks=(
                    original.breaks[0],
                    BreakRecord("", 1, 740, 760),
                ),
                fields=frozenset(("breaks",)),
            )

        preserved = self.repository.load_month(2024, 6).days[0]
        self.assertEqual(preserved.breaks, original.breaks)
        self.assertEqual(preserved.revision, original.revision)

    def test_close_is_atomic_and_successor_carry_refreshes_only_when_visited(self):
        june = self.repository.get_or_create_month(2024, 6)
        july = self.repository.get_or_create_month(2024, 7)
        first = june.days[2]
        self.repository.update_day(
            first.work_date,
            expected_revision=first.revision,
            start_minute=480,
            end_minute=1020,
            break_duration_minutes=30,
            fields=frozenset(("start_minute", "end_minute", "break_duration_minutes")),
        )

        closed = self.repository.close_month(
            2024,
            6,
            expected_revision=june.revision,
            mark_unresolved_no_data=True,
        )
        self.assertEqual(closed.status, "closed")
        self.assertEqual(closed.closing_balance_minutes, 30)
        self.assertEqual(self.repository.load_month(2024, 7).opening_balance_minutes, 0)
        self.assertEqual(
            self.repository.get_or_create_month(2024, 7).opening_balance_minutes,
            30,
        )
        self.assertEqual(
            self.sql.execute(
                """
                SELECT COUNT(*) FROM closed_day_results result
                JOIN day_entries day ON day.id = result.day_entry_id
                JOIN months month ON month.id = day.month_id
                WHERE month.year = 2024 AND month.month = 6
                """
            ).fetchone()[0],
            len(closed.days),
        )
        with self.assertRaises(ClosedPeriodError):
            self.repository.update_day(
                first.work_date,
                expected_revision=first.revision + 1,
                special_day="Changed",
                fields=frozenset(("special_day",)),
            )
        reopened = self.repository.reopen_month(
            2024, 6, expected_revision=closed.revision
        )
        self.assertEqual(reopened.status, "open")
        self.assertTrue(all(day.daily_overtime_minutes is None for day in reopened.days))
        changed = self.repository.update_day(
            first.work_date,
            expected_revision=reopened.days[2].revision,
            special_day="Changed",
            fields=frozenset(("special_day",)),
        )
        self.assertEqual(changed.special_day, "Changed")

    def test_close_requires_blank_normal_days_to_be_explicitly_classified(self):
        month = self.repository.get_or_create_month(2024, 6)
        preview = self.repository.preview_month_close(2024, 6)

        self.assertTrue(preview.unresolved_days)
        self.assertTrue(all(item.weekday() < 5 for item in preview.unresolved_days))
        with self.assertRaisesRegex(StorageValidationError, "No data"):
            self.repository.close_month(
                2024, 6, expected_revision=month.revision
            )

        closed = self.repository.close_month(
            2024,
            6,
            expected_revision=month.revision,
            mark_unresolved_no_data=True,
        )
        classified = {
            day.work_date for day in closed.days if day.special_day == "No data"
        }
        self.assertEqual(classified, set(preview.unresolved_days))

    def test_current_month_can_close_when_unresolved_days_are_confirmed_no_data(self):
        today = date.today()
        month = self.repository.get_or_create_month(today.year, today.month)

        closed = self.repository.close_month(
            today.year,
            today.month,
            expected_revision=month.revision,
            mark_unresolved_no_data=True,
        )

        self.assertEqual(closed.status, "closed")

    def test_future_month_close_is_rejected_without_reclassifying_days(self):
        today = date.today()
        year, month_number = (
            (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
        )
        month = self.repository.get_or_create_month(year, month_number)

        with self.assertRaisesRegex(StorageValidationError, "future month"):
            self.repository.close_month(
                year,
                month_number,
                expected_revision=month.revision,
                mark_unresolved_no_data=True,
            )

        preserved = self.repository.load_month(year, month_number)
        self.assertEqual(preserved.status, "open")
        self.assertTrue(all(day.special_day == "Normal day" for day in preserved.days))

    def test_special_day_work_adds_all_worked_minutes(self):
        month = self.repository.get_or_create_month(2024, 6)
        monday = next(day for day in month.days if day.work_date.weekday() == 0)
        self.repository.update_day(
            monday.work_date,
            expected_revision=monday.revision,
            special_day="Vacation",
            start_minute=480,
            end_minute=720,
            break_duration_minutes=0,
            fields=frozenset(
                ("special_day", "start_minute", "end_minute", "break_duration_minutes")
            ),
        )

        closed = self.repository.close_month(
            2024,
            6,
            expected_revision=month.revision,
            mark_unresolved_no_data=True,
        )

        stored = next(day for day in closed.days if day.work_date == monday.work_date)
        self.assertEqual(stored.expected_work_minutes, 480)
        self.assertEqual(stored.daily_overtime_minutes, 240)

    def test_open_csv_export_uses_zero_expectation_for_special_day(self):
        month = self.repository.get_or_create_month(2024, 6)
        monday = next(day for day in month.days if day.work_date.weekday() == 0)
        self.repository.update_day(
            monday.work_date,
            expected_revision=monday.revision,
            special_day="Vacation",
            start_minute=480,
            end_minute=720,
            break_duration_minutes=0,
            fields=frozenset(
                ("special_day", "start_minute", "end_minute", "break_duration_minutes")
            ),
        )
        target = Path(self.temporary.name) / "special.csv"

        export_month(self.repository.load_month(2024, 6), target)

        with target.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.reader(stream))
        exported = next(row for row in rows[1:] if row[0] == monday.work_date.strftime("%d.%m.%Y"))
        self.assertEqual(exported[5], "04:00")

    def test_configured_weekend_expectation_is_authoritative(self):
        self._replace_schedule(
            effective_from=date(2024, 6, 1),
            effective_to=None,
            weekday_minutes=(480, 480, 480, 480, 480, 240, 0),
        )
        month = self.repository.get_or_create_month(2024, 6)
        saturday = next(day for day in month.days if day.work_date.weekday() == 5)
        self.assertIn(saturday.work_date, self.repository.preview_month_close(2024, 6).unresolved_days)
        self.repository.update_day(
            saturday.work_date,
            expected_revision=saturday.revision,
            start_minute=480,
            end_minute=600,
            break_duration_minutes=0,
            fields=frozenset(("start_minute", "end_minute", "break_duration_minutes")),
        )

        closed = self.repository.close_month(
            2024,
            6,
            expected_revision=month.revision,
            mark_unresolved_no_data=True,
        )

        stored = next(day for day in closed.days if day.work_date == saturday.work_date)
        self.assertEqual(stored.daily_overtime_minutes, -120)

    def test_reopened_history_can_be_reclosed_without_rewriting_closed_successor(self):
        january = self.repository.get_or_create_month(2024, 1)
        february = self.repository.get_or_create_month(2024, 2)
        with self.assertRaisesRegex(StorageValidationError, "earlier month"):
            self.repository.close_month(
                2024, 2, expected_revision=february.revision,
                mark_unresolved_no_data=True,
            )
        january = self.repository.close_month(
            2024, 1, expected_revision=january.revision,
            mark_unresolved_no_data=True,
        )
        february = self.repository.get_or_create_month(2024, 2)
        february = self.repository.close_month(
            2024, 2, expected_revision=february.revision,
            mark_unresolved_no_data=True,
        )
        january = self.repository.reopen_month(
            2024, 1, expected_revision=january.revision
        )
        first = january.days[0]
        self.repository.update_day(
            first.work_date,
            expected_revision=first.revision,
            special_day="Normal day",
            start_minute=480,
            end_minute=1020,
            break_duration_minutes=30,
            fields=frozenset(
                ("special_day", "start_minute", "end_minute", "break_duration_minutes")
            ),
        )
        january = self.repository.close_month(
            2024, 1, expected_revision=january.revision
        )

        preserved_february = self.repository.load_month(2024, 2)
        self.assertEqual(january.closing_balance_minutes, 30)
        self.assertEqual(preserved_february, february)
        self.assertTrue(self.repository.month_has_carry_discontinuity(2024, 2))

    def test_direct_sql_close_requires_a_valid_running_balance_chain(self):
        month = self.repository.get_or_create_month(2024, 6)
        month_id = self.sql.execute(
            "SELECT id FROM months WHERE year = 2024 AND month = 6"
        ).fetchone()[0]
        self.sql.execute(
            """
            INSERT INTO closed_day_results(
                day_entry_id, daily_overtime_minutes, running_balance_minutes
            )
            SELECT id, 0, 0 FROM day_entries WHERE month_id = ?
            """,
            (month_id,),
        )
        first_day_id = self.sql.execute(
            "SELECT id FROM day_entries WHERE month_id = ? ORDER BY work_date LIMIT 1",
            (month_id,),
        ).fetchone()[0]
        self.sql.execute(
            "UPDATE closed_day_results SET running_balance_minutes = 10 WHERE day_entry_id = ?",
            (first_day_id,),
        )

        with self.assertRaises(sqlite3.IntegrityError):
            self.sql.execute(
                """
                UPDATE months SET status = 'closed', closing_balance_minutes = 0,
                    closed_at = '2024-07-01T00:00:00Z'
                WHERE id = ? AND revision = ?
                """,
                (month_id, month.revision),
            )

    def test_direct_sql_reopen_allows_only_lifecycle_fields_and_clears_results(self):
        month = self.repository.get_or_create_month(2024, 6)
        closed = self.repository.close_month(
            2024,
            6,
            expected_revision=month.revision,
            mark_unresolved_no_data=True,
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.sql.execute(
                """
                UPDATE months SET status = 'open', opening_balance_minutes = 1,
                    closing_balance_minutes = NULL, closed_at = NULL,
                    updated_at = '2024-07-01T00:00:00Z', revision = revision + 1
                WHERE year = 2024 AND month = 6
                """
            )
        self.sql.execute(
            """
            UPDATE months SET status = 'open', closing_balance_minutes = NULL,
                closed_at = NULL, updated_at = '2024-07-01T00:00:00Z',
                revision = revision + 1
            WHERE year = 2024 AND month = 6 AND revision = ?
            """,
            (closed.revision,),
        )
        self.assertEqual(
            self.sql.execute(
                """
                SELECT COUNT(*) FROM closed_day_results result
                JOIN day_entries day ON day.id = result.day_entry_id
                JOIN months month ON month.id = day.month_id
                WHERE month.year = 2024 AND month.month = 6
                """
            ).fetchone()[0],
            0,
        )

    def test_schema_has_no_independent_active_workday_state(self):
        table = self.sql.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'active_workday'"
        ).fetchone()

        self.assertIsNone(table)

    def test_startup_rejects_a_replaced_business_trigger(self):
        self.sql.execute("DROP TRIGGER day_guard_delete")
        self.sql.execute(
            """
            CREATE TRIGGER day_guard_delete
            BEFORE DELETE ON day_entries
            WHEN 0
            BEGIN SELECT RAISE(ABORT, 'disabled'); END
            """
        )

        with self.assertRaisesRegex(StorageCorrupt, "day_guard_delete"):
            SQLiteRepository(self.path)

    def test_startup_rejects_a_missing_required_index(self):
        self.sql.execute("DROP INDEX one_open_break_per_day")

        with self.assertRaisesRegex(StorageCorrupt, "one_open_break_per_day"):
            SQLiteRepository(self.path)

    def test_startup_rejects_an_unexpected_table_column(self):
        self.sql.execute("ALTER TABLE datasets ADD COLUMN untrusted_value TEXT")

        with self.assertRaisesRegex(StorageCorrupt, "datasets"):
            SQLiteRepository(self.path)

    def test_v1_database_drops_only_obsolete_active_state_on_upgrade(self):
        legacy_path = Path(self.temporary.name) / "v1.db"
        legacy = SQLiteRepository.create(legacy_path)
        legacy.start_workday(
            date(2024, 6, 3),
            480,
            datetime(2024, 6, 3, 8, tzinfo=timezone.utc),
        )
        legacy.close()

        sql = sqlite3.connect(legacy_path, isolation_level=None)
        day_id = sql.execute(
            "SELECT id FROM day_entries WHERE work_date = '2024-06-03'"
        ).fetchone()[0]
        sql.execute(
            """
            CREATE TABLE active_workday (
                singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
                day_entry_id INTEGER NOT NULL UNIQUE REFERENCES day_entries(id),
                started_at_utc TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                revision INTEGER NOT NULL DEFAULT 1
            ) STRICT
            """
        )
        sql.execute(
            """
            INSERT INTO active_workday(singleton_id, day_entry_id, started_at_utc, updated_at)
            VALUES (1, ?, '2024-06-03T08:00:00Z', '2024-06-03T08:00:00Z')
            """,
            (day_id,),
        )
        sql.execute("UPDATE schema_migrations SET version = 1")
        sql.execute("PRAGMA user_version = 1")
        sql.close()

        upgraded = SQLiteRepository(legacy_path)
        try:
            recovered = upgraded.load_month(2024, 6).days[2]
            self.assertEqual(recovered.start_minute, 480)
            self.assertIsNone(recovered.end_minute)
            table = upgraded._connection.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type = 'table' AND name = 'active_workday'"
            ).fetchone()
            self.assertIsNone(table)
            self.assertEqual(
                upgraded._connection.execute("PRAGMA user_version").fetchone()[0],
                SCHEMA_VERSION,
            )
        finally:
            upgraded.close()

    def test_v3_upgrade_marks_preexisting_closed_day_changes_as_local(self):
        legacy_path = Path(self.temporary.name) / "v3.db"
        legacy = SQLiteRepository.create(legacy_path)
        month = legacy.get_or_create_month(2024, 6)
        legacy.update_day(
            date(2024, 6, 3),
            expected_revision=month.days[2].revision,
            special_day="Vacation",
            fields=frozenset(("special_day",)),
        )
        legacy.close_month(
            2024, 6, expected_revision=month.revision,
            mark_unresolved_no_data=True,
        )
        legacy.close()

        sql = sqlite3.connect(legacy_path, isolation_level=None)
        sql.execute("ALTER TABLE day_entries DROP COLUMN local_input_revision")
        sql.execute("UPDATE schema_migrations SET version = 3")
        sql.execute("PRAGMA user_version = 3")
        sql.close()

        upgraded = SQLiteRepository(legacy_path)
        try:
            stored = upgraded._connection.execute(
                """
                SELECT revision, local_input_revision FROM day_entries
                WHERE work_date = '2024-06-03'
                """
            ).fetchone()
            self.assertEqual(tuple(stored), (2, 1))
            self.assertEqual(
                upgraded._connection.execute("PRAGMA user_version").fetchone()[0],
                SCHEMA_VERSION,
            )
            with self.assertRaises(sqlite3.IntegrityError):
                upgraded._connection.execute(
                    """
                    UPDATE day_entries SET special_day = 'Changed'
                    WHERE work_date = '2024-06-03'
                    """
                )
        finally:
            upgraded.close()

    def test_v4_upgrade_canonicalizes_historical_schema_without_changing_data(self):
        legacy_path = Path(self.temporary.name) / "v4.db"
        legacy = SQLiteRepository.create(legacy_path)
        month = legacy.get_or_create_month(2024, 6)
        legacy.update_day(
            date(2024, 6, 3),
            expected_revision=month.days[2].revision,
            special_day="Vacation",
            fields=frozenset(("special_day",)),
        )
        expected = legacy.load_month(2024, 6)
        legacy.close()

        sql = sqlite3.connect(legacy_path, isolation_level=None)
        canonical_schedule_sql = sql.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type = 'table' AND name = 'work_schedule_periods'"
        ).fetchone()[0]
        historical_schedule_sql = canonical_schedule_sql.replace(
            """CHECK (
        date(effective_from, '+0 days') IS NOT NULL
        AND effective_from = date(effective_from, '+0 days')
    ),
    CHECK (
        effective_to IS NULL OR (
            date(effective_to, '+0 days') IS NOT NULL
            AND effective_to = date(effective_to, '+0 days')
        )
    ),""",
            """CHECK (effective_from = date(effective_from, '+0 days')),
    CHECK (effective_to IS NULL OR effective_to = date(effective_to, '+0 days')),""",
        )
        self.assertNotEqual(historical_schedule_sql, canonical_schedule_sql)
        sql.execute("PRAGMA legacy_alter_table = ON")
        sql.execute(
            "ALTER TABLE work_schedule_periods RENAME TO work_schedule_periods_v4_test"
        )
        sql.execute(historical_schedule_sql)
        schedule_columns = ", ".join(
            row[1] for row in sql.execute("PRAGMA table_info(work_schedule_periods)")
        )
        sql.execute(
            f"INSERT INTO work_schedule_periods({schedule_columns}) "
            f"SELECT {schedule_columns} FROM work_schedule_periods_v4_test"
        )
        sql.execute("DROP TABLE work_schedule_periods_v4_test")
        sql.execute("PRAGMA legacy_alter_table = OFF")
        sql.execute(
            """
            CREATE TRIGGER month_no_insert_before_closed
            BEFORE INSERT ON months
            WHEN EXISTS (SELECT 1 FROM months WHERE status = 'closed')
            BEGIN SELECT RAISE(ABORT, 'obsolete month insertion guard'); END
            """
        )
        sql.execute("DROP TRIGGER closed_month_no_update")
        sql.execute(
            """
            CREATE TRIGGER closed_month_no_update
            BEFORE UPDATE ON months
            WHEN OLD.status = 'closed'
            BEGIN SELECT RAISE(ABORT, 'closed month is immutable'); END
            """
        )
        sql.execute("UPDATE schema_migrations SET version = 4")
        sql.execute("PRAGMA user_version = 4")
        sql.close()

        upgraded = SQLiteRepository(legacy_path)
        try:
            self.assertEqual(upgraded.load_month(2024, 6), expected)
            self.assertEqual(
                upgraded._connection.execute("PRAGMA user_version").fetchone()[0],
                SCHEMA_VERSION,
            )
            trigger_sql = upgraded._connection.execute(
                "SELECT sql FROM sqlite_master "
                "WHERE type = 'trigger' AND name = 'closed_month_no_update'"
            ).fetchone()[0]
            self.assertIn("ZT:CLOSED_PERIOD:MONTH_IMMUTABLE", trigger_sql)
            self.assertNotIn("closed month is immutable", trigger_sql)
            obsolete = upgraded._connection.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type = 'trigger' AND name = 'month_no_insert_before_closed'"
            ).fetchone()
            self.assertIsNone(obsolete)
            recovery_root = legacy_path.parent / "recovery"
            self.assertTrue(recovery_root.is_dir())
            self.assertEqual(tuple(recovery_root.iterdir()), ())
        finally:
            upgraded.close()

    def test_failed_migration_chain_rolls_back_and_retains_verified_backup(self):
        legacy_path = Path(self.temporary.name) / "v3-chain.db"
        legacy = SQLiteRepository.create(legacy_path)
        legacy.get_or_create_month(2024, 6)
        legacy.close()

        sql = sqlite3.connect(legacy_path, isolation_level=None)
        sql.execute("ALTER TABLE day_entries DROP COLUMN local_input_revision")
        sql.execute("UPDATE schema_migrations SET version = 3")
        sql.execute("PRAGMA user_version = 3")
        sql.close()

        with patch.dict(
            "znactime.storage.sqlite.repository.MIGRATIONS",
            {4: "THIS IS NOT VALID SQL;"},
        ):
            with self.assertRaisesRegex(StorageError, "Recovery backup:") as raised:
                SQLiteRepository(legacy_path)

        self.assertEqual(
            raised.exception.recovery_backup_path,
            next((legacy_path.parent / "recovery").glob("*/v3-chain.db")),
        )
        self.assertTrue(raised.exception.migration_signature)

        source = sqlite3.connect(legacy_path)
        try:
            self.assertEqual(source.execute("PRAGMA user_version").fetchone()[0], 3)
            columns = {
                row[1] for row in source.execute("PRAGMA table_info(day_entries)")
            }
            self.assertNotIn("local_input_revision", columns)
        finally:
            source.close()

        backups = tuple((legacy_path.parent / "recovery").glob("*/v3-chain.db"))
        self.assertEqual(len(backups), 1)
        backup = sqlite3.connect(backups[0])
        try:
            self.assertEqual(backup.execute("PRAGMA quick_check").fetchone()[0], "ok")
            self.assertEqual(backup.execute("PRAGMA user_version").fetchone()[0], 3)
            self.assertEqual(
                backup.execute("SELECT COUNT(*) FROM months").fetchone()[0],
                1,
            )
        finally:
            backup.close()

    def test_direct_sql_rejects_malformed_day_and_schedule_dates(self):
        self.repository.get_or_create_month(2024, 6)
        month_id = self.sql.execute(
            "SELECT id FROM months WHERE year = 2024 AND month = 6"
        ).fetchone()[0]
        now = "2024-06-01T00:00:00Z"
        invalid_dates = (
            "2024-06-invalid",
            "2024-06-31",
            "2024-06-00",
            "2023-02-29",
            "2024-13-01",
            "2024-6-1",
            "2024-06-01T00:00:00",
            "",
        )

        for invalid in invalid_dates:
            with self.subTest(day=invalid), self.assertRaises(sqlite3.IntegrityError):
                self.sql.execute(
                    """
                    INSERT INTO day_entries(
                        month_id, work_date, special_day, expected_work_minutes,
                        created_at, updated_at
                    ) VALUES (?, ?, 'Normal day', 480, ?, ?)
                    """,
                    (month_id, invalid, now, now),
                )

            with self.subTest(schedule=invalid), self.assertRaises(
                sqlite3.IntegrityError
            ):
                self.sql.execute(
                    """
                    UPDATE work_schedule_periods SET effective_to = ?
                    WHERE dataset_id = (SELECT id FROM datasets)
                    """,
                    (invalid,),
                )

    def test_v2_upgrade_refuses_preexisting_malformed_dates(self):
        invalid_path = Path(self.temporary.name) / "invalid-v2.db"
        repository = SQLiteRepository.create(invalid_path)
        repository.get_or_create_month(2024, 6)
        repository.close()

        sql = sqlite3.connect(invalid_path, isolation_level=None)
        sql.execute("DROP TRIGGER day_date_valid_insert")
        sql.execute("DROP TRIGGER day_date_valid_update")
        sql.execute("PRAGMA ignore_check_constraints = ON")
        month_id = sql.execute(
            "SELECT id FROM months WHERE year = 2024 AND month = 6"
        ).fetchone()[0]
        sql.execute(
            """
            INSERT INTO day_entries(
                month_id, work_date, special_day, expected_work_minutes,
                created_at, updated_at
            ) VALUES (?, '2024-06-invalid', 'Normal day', 480,
                      '2024-06-01T00:00:00Z', '2024-06-01T00:00:00Z')
            """,
            (month_id,),
        )
        sql.execute("UPDATE schema_migrations SET version = 2")
        sql.execute("PRAGMA user_version = 2")
        sql.close()

        with self.assertRaises(StorageCorrupt):
            SQLiteRepository(invalid_path)

    def test_schedule_changes_only_open_non_overridden_days(self):
        month = self.repository.get_or_create_month(2024, 6)
        override = month.days[0]
        self.repository.set_day_work_limit(
            override.work_date, 300, expected_revision=override.revision
        )
        self._replace_schedule(
            effective_from=date(2024, 6, 1),
            effective_to=None,
            weekday_minutes=(420, 420, 420, 420, 420, 0, 0),
        )
        changed = self.repository.load_month(2024, 6)
        self.assertEqual(changed.days[0].expected_work_minutes, 300)
        self.assertEqual(changed.days[1].expected_work_minutes, 0)
        self.assertEqual(changed.days[3].expected_work_minutes, 420)

    def test_backdated_schedule_is_bounded_by_the_following_period(self):
        self.repository.get_or_create_month(2024, 5)
        self.repository.get_or_create_month(2024, 6)
        self.repository.get_or_create_month(2024, 7)
        self._replace_schedule(
            effective_from=date(2024, 6, 1),
            effective_to=None,
            weekday_minutes=(420, 420, 420, 420, 420, 0, 0),
        )
        later_revisions = dict(
            self.sql.execute(
                """
                SELECT work_date, revision FROM day_entries
                WHERE work_date >= '2024-06-01'
                """
            ).fetchall()
        )

        may = self._replace_schedule(
            effective_from=date(2024, 5, 1),
            effective_to=date(2024, 5, 31),
            weekday_minutes=(450, 450, 450, 450, 450, 0, 0),
        )

        self.assertEqual(may.effective_to, date(2024, 5, 31))
        june = next(
            item
            for item in self.repository.list_work_schedules()
            if item.effective_from == date(2024, 6, 1)
        )
        self.assertIsNone(june.effective_to)
        self.assertEqual(
            dict(
                self.sql.execute(
                    """
                    SELECT work_date, revision FROM day_entries
                    WHERE work_date >= '2024-06-01'
                    """
                ).fetchall()
            ),
            later_revisions,
        )

    def test_schedule_updates_only_changed_values_and_exact_noop_changes_nothing(self):
        self.repository.get_or_create_month(2024, 6)
        period = self._replace_schedule(
            effective_from=date(2024, 6, 1),
            effective_to=None,
            weekday_minutes=(480, 480, 480, 480, 480, 0, 0),
        )
        rows = self.sql.execute(
            """
            SELECT work_date, revision FROM day_entries ORDER BY work_date
            """
        ).fetchall()
        self.assertTrue(all(revision == 1 for _work_date, revision in rows))

        repeated = self._replace_schedule(
            effective_from=date(2024, 6, 1),
            effective_to=None,
            weekday_minutes=(480, 480, 480, 480, 480, 0, 0),
        )

        self.assertEqual(repeated.revision, period.revision)
        self.assertEqual(
            self.sql.execute(
                "SELECT work_date, revision FROM day_entries ORDER BY work_date"
            ).fetchall(),
            rows,
        )

    def test_schedule_write_rejects_a_stale_active_revision(self):
        effective_from = date(2024, 6, 1)
        self._replace_schedule(
            effective_from=effective_from,
            effective_to=None,
            weekday_minutes=(420, 420, 420, 420, 420, 0, 0),
        )
        stale = next(
            item
            for item in self.repository.list_work_schedules()
            if item.effective_from == effective_from
        )
        other = SQLiteRepository(self.path)
        try:
            winner = other.replace_work_schedule(
                effective_from=effective_from,
                effective_to=None,
                weekday_minutes=(450, 450, 450, 450, 450, 0, 0),
                expected_public_id=stale.public_id,
                expected_revision=stale.revision,
            )

            with self.assertRaisesRegex(StorageConflict, "changed since"):
                self.repository.replace_work_schedule(
                    effective_from=effective_from,
                    effective_to=None,
                    weekday_minutes=(480, 480, 480, 480, 480, 0, 0),
                    expected_public_id=stale.public_id,
                    expected_revision=stale.revision,
                )
        finally:
            other.close()

        current = next(
            item
            for item in self.repository.list_work_schedules()
            if item.effective_from == effective_from
        )
        self.assertEqual(current.revision, winner.revision)
        self.assertEqual(current.weekday_minutes, winner.weekday_minutes)

    def test_schedule_write_rejects_a_stale_active_identity(self):
        effective_from = date(2024, 6, 1)
        stale = self.repository.list_work_schedules()[0]
        other = SQLiteRepository(self.path)
        try:
            winner = other.replace_work_schedule(
                effective_from=effective_from,
                effective_to=None,
                weekday_minutes=(450, 450, 450, 450, 450, 0, 0),
                expected_public_id=stale.public_id,
                expected_revision=stale.revision,
            )

            with self.assertRaisesRegex(StorageConflict, "changed since"):
                self.repository.replace_work_schedule(
                    effective_from=effective_from,
                    effective_to=None,
                    weekday_minutes=(480, 480, 480, 480, 480, 0, 0),
                    expected_public_id=stale.public_id,
                    expected_revision=stale.revision,
                )
        finally:
            other.close()

        current = next(
            item
            for item in self.repository.list_work_schedules()
            if item.effective_from == effective_from
        )
        self.assertEqual(current.public_id, winner.public_id)
        self.assertEqual(current.weekday_minutes, winner.weekday_minutes)

    def test_local_input_revision_is_sticky_across_automatic_schedule_changes(self):
        work_date = date(2024, 6, 3)
        day = self.repository.get_or_create_month(2024, 6).days[2]
        self._replace_schedule(
            effective_from=date(2024, 6, 1),
            effective_to=None,
            weekday_minutes=(420, 420, 420, 420, 420, 0, 0),
        )
        after_schedule = self.sql.execute(
            """
            SELECT revision, local_input_revision FROM day_entries
            WHERE work_date = ?
            """,
            (work_date.isoformat(),),
        ).fetchone()
        self.assertEqual(tuple(after_schedule), (day.revision + 1, 0))

        changed = self.repository.load_month(2024, 6).days[2]
        changed = self.repository.update_day(
            work_date,
            expected_revision=changed.revision,
            special_day="Vacation",
            fields=frozenset(("special_day",)),
        )
        self.repository.update_day(
            work_date,
            expected_revision=changed.revision,
            special_day="Normal day",
            fields=frozenset(("special_day",)),
        )
        before_automatic_change = self.sql.execute(
            """
            SELECT local_input_revision FROM day_entries WHERE work_date = ?
            """,
            (work_date.isoformat(),),
        ).fetchone()[0]

        self._replace_schedule(
            effective_from=date(2024, 6, 1),
            effective_to=None,
            weekday_minutes=(450, 450, 450, 450, 450, 0, 0),
        )

        after_automatic_change = self.sql.execute(
            """
            SELECT expected_work_minutes, local_input_revision
            FROM day_entries WHERE work_date = ?
            """,
            (work_date.isoformat(),),
        ).fetchone()
        self.assertEqual(before_automatic_change, 2)
        self.assertEqual(tuple(after_automatic_change), (450, 2))

    def test_workday_transitions_are_derived_from_day_data(self):
        work_date = date(2024, 6, 3)
        now = datetime(2024, 6, 3, 8, tzinfo=timezone.utc)
        started = self.repository.start_workday(work_date, 480, now)
        self.assertEqual(started.start_minute, 480)

        paused = self.repository.start_pause(work_date, 720, now)
        self.assertIsNone(paused.breaks[0].end_minute)
        resumed = self.repository.resume_workday(work_date, 750, now)
        self.assertEqual(resumed.breaks[0].end_minute, 750)
        stopped = self.repository.stop_workday(work_date, 1020, now)
        self.assertEqual(stopped.end_minute, 1020)
        stored = self.repository.load_month(2024, 6).days[2]
        self.assertEqual(stored.start_minute, 480)
        self.assertEqual(stored.end_minute, 1020)
        self.assertEqual(stored.breaks[0].end_minute, 750)

    def test_invalid_stop_preserves_running_day_and_open_pause(self):
        work_date = date(2024, 6, 3)
        now = datetime(2024, 6, 3, 8, tzinfo=timezone.utc)
        self.repository.start_workday(work_date, 480, now)
        paused = self.repository.start_pause(work_date, 540, now)

        for invalid_end in (480, 400):
            with self.subTest(end=invalid_end), self.assertRaisesRegex(
                StorageValidationError,
                "later than start",
            ):
                self.repository.stop_workday(work_date, invalid_end, now)

        preserved = self.repository.load_month(2024, 6).days[2]
        self.assertIsNone(preserved.end_minute)
        self.assertEqual(preserved.breaks, paused.breaks)
        self.assertEqual(preserved.revision, paused.revision)

    def test_workday_transitions_reject_naive_timestamps_before_writing(self):
        work_date = date(2024, 6, 3)
        naive = datetime(2024, 6, 3, 8)
        aware = naive.replace(tzinfo=timezone.utc)

        with self.assertRaises(StorageValidationError):
            self.repository.start_workday(work_date, 480, naive)
        self.assertIsNone(self.repository.load_month(2024, 6))

        self.repository.start_workday(work_date, 480, aware)
        with self.assertRaises(StorageValidationError):
            self.repository.start_pause(work_date, 720, naive)
        running = self.repository.load_month(2024, 6).days[2]
        self.assertEqual(running.breaks, ())

        self.repository.start_pause(work_date, 720, aware)
        with self.assertRaises(StorageValidationError):
            self.repository.resume_workday(work_date, 750, naive)
        paused = self.repository.load_month(2024, 6).days[2]
        self.assertIsNone(paused.breaks[0].end_minute)

        with self.assertRaises(StorageValidationError):
            self.repository.stop_workday(work_date, 1020, naive)
        still_running = self.repository.load_month(2024, 6).days[2]
        self.assertIsNone(still_running.end_minute)

    def test_aware_local_timestamp_is_converted_to_real_utc(self):
        work_date = date(2024, 6, 3)
        berlin_summer = datetime(
            2024,
            6,
            3,
            8,
            tzinfo=timezone(timedelta(hours=2)),
        )

        self.repository.start_workday(work_date, 480, berlin_summer)

        stored = self.sql.execute(
            "SELECT updated_at FROM day_entries WHERE work_date = ?",
            (work_date.isoformat(),),
        ).fetchone()[0]
        self.assertEqual(stored, "2024-06-03T06:00:00Z")

    def test_pause_requires_explicit_replacement_of_nonzero_duration(self):
        work_date = date(2024, 6, 3)
        now = datetime(2024, 6, 3, 8, tzinfo=timezone.utc)
        started = self.repository.start_workday(work_date, 480, now)
        duration = self.repository.update_day(
            work_date,
            expected_revision=started.revision,
            break_duration_minutes=30,
            fields=frozenset(("break_duration_minutes",)),
        )

        with self.assertRaises(StorageConflict):
            self.repository.start_pause(work_date, 720, now)

        preserved = self.repository.load_month(2024, 6).days[2]
        self.assertEqual(preserved.break_duration_minutes, 30)
        self.assertEqual(preserved.breaks, ())
        self.assertEqual(preserved.revision, duration.revision)

        replaced = self.repository.start_pause(
            work_date,
            720,
            now,
            replace_duration=True,
        )
        self.assertIsNone(replaced.break_duration_minutes)
        self.assertEqual(len(replaced.breaks), 1)
        self.assertEqual(replaced.breaks[0].start_minute, 720)
        self.assertIsNone(replaced.breaks[0].end_minute)

    def test_open_workday_survives_restart_using_only_day_data(self):
        work_date = date(2024, 6, 17)
        started_at = datetime(2024, 6, 17, 8, tzinfo=timezone.utc)
        self.repository.start_workday(work_date, 480, started_at)
        self.repository.start_pause(work_date, 750, started_at)

        self.repository.close()
        self.repository = SQLiteRepository(self.path)
        recovered = self.repository.load_month(2024, 6).days[16]

        self.assertEqual(recovered.start_minute, 480)
        self.assertIsNone(recovered.end_minute)
        self.assertEqual(recovered.breaks[0].start_minute, 750)
        self.assertIsNone(recovered.breaks[0].end_minute)

        resumed = self.repository.resume_workday(work_date, 780, started_at)
        stopped = self.repository.stop_workday(work_date, 1020, started_at)
        self.assertEqual(resumed.breaks[0].end_minute, 780)
        self.assertEqual(stopped.end_minute, 1020)

    def test_verified_backup_reopens(self):
        self.repository.get_or_create_month(2024, 2)
        backup = Path(self.temporary.name) / "backup" / "copy.db"
        self.repository.backup_to(backup)
        with self.assertRaises(StorageConflict):
            self.repository.backup_to(backup)
        self.repository.get_or_create_month(2024, 3)
        self.repository.backup_to(backup, overwrite=True)
        copied = SQLiteRepository(backup)
        try:
            self.assertEqual(len(copied.load_month(2024, 2).days), 29)
            self.assertEqual(len(copied.load_month(2024, 3).days), 31)
        finally:
            copied.close()

    def test_backup_rejects_live_database_and_hard_link_alias(self):
        alias = Path(self.temporary.name) / "database-alias.db"
        os.link(self.path, alias)

        for destination in (self.path, alias):
            with self.subTest(destination=destination):
                with self.assertRaises(StorageConflict):
                    self.repository.backup_to(destination, overwrite=True)

        self.assertEqual(self.sql.execute("PRAGMA quick_check").fetchone()[0], "ok")

    def test_cancelled_backup_leaves_no_destination_or_temporary_file(self):
        self.repository.get_or_create_month(2024, 2)
        destination = Path(self.temporary.name) / "backup" / "cancelled.db"
        checks = 0

        def cancelled():
            nonlocal checks
            checks += 1
            return checks > 1

        with self.assertRaises(LegacyImportCancelled):
            self.repository.backup_to(destination, cancelled=cancelled)

        self.assertFalse(destination.exists())
        self.assertEqual(list(destination.parent.glob(".*.tmp")), [])

    def test_csv_export_is_legacy_compatible_and_atomic(self):
        month = self.repository.get_or_create_month(2024, 2)
        target = Path(self.temporary.name) / "exports" / "2024_tmp_02.csv"
        export_month(month, target)

        exported_root = Path(self.temporary.name) / "exports-root" / "2024"
        exported_root.mkdir(parents=True)
        exported = exported_root / target.name
        target.replace(exported)
        preflight = preflight_legacy_data(exported_root.parent)
        self.assertFalse(preflight.blocking_errors)
        self.assertEqual(len(preflight.months[0].days), 29)
        with self.assertRaises(FileExistsError):
            export_month(month, exported)

    def test_csv_export_rejects_active_database_destination(self):
        month = self.repository.get_or_create_month(2024, 2)

        with self.assertRaises(StorageConflict):
            export_month(
                month,
                self.path,
                overwrite=True,
                protected_paths=sqlite_protected_paths(self.path),
            )

        self.assertEqual(self.sql.execute("PRAGMA quick_check").fetchone()[0], "ok")

    def test_csv_export_is_spreadsheet_safe_and_reimports_exact_text(self):
        month = self.repository.get_or_create_month(2024, 2)
        special_values = (
            "=1+1",
            "+SUM(A1:A2)",
            "-1+2",
            "@command",
            "'=literal apostrophe",
        )
        for day, special in zip(month.days, special_values):
            changed = self.repository.update_day(
                day.work_date,
                expected_revision=day.revision,
                special_day=special,
                fields=frozenset(("special_day",)),
            )
            self.assertEqual(changed.special_day, special)

        export_root = Path(self.temporary.name) / "safe-export"
        year_dir = export_root / "2024"
        year_dir.mkdir(parents=True)
        target = year_dir / "2024_tmp_02.csv"
        export_month(self.repository.load_month(2024, 2), target)

        with target.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.reader(stream))
        self.assertEqual(rows[0], ["#znacTime-csv", "3"])
        self.assertEqual(
            [row[1] for row in rows[1:1 + len(special_values)]],
            [spreadsheet_safe_text(value) for value in special_values],
        )

        imported = preflight_legacy_data(export_root)
        self.assertFalse(imported.blocking_errors)
        self.assertEqual(
            [day.special_day for day in imported.months[0].days[:len(special_values)]],
            list(special_values),
        )

    def test_special_day_text_is_bounded_before_storage_and_export(self):
        month = self.repository.get_or_create_month(2024, 2)
        day = month.days[0]
        for invalid in (
            "control\ttext",
            "line\nbreak",
            "x" * (MAX_SPECIAL_DAY_LENGTH + 1),
        ):
            with self.assertRaises(StorageValidationError):
                self.repository.update_day(
                    day.work_date,
                    expected_revision=day.revision,
                    special_day=invalid,
                    fields=frozenset(("special_day",)),
                )

        maximum = "x" * MAX_SPECIAL_DAY_LENGTH
        stored = self.repository.update_day(
            day.work_date,
            expected_revision=day.revision,
            special_day=maximum,
            fields=frozenset(("special_day",)),
        )
        self.assertEqual(stored.special_day, maximum)

        unsafe_month = replace(
            month,
            days=(replace(day, special_day="control\rtext"), *month.days[1:]),
        )
        destination = Path(self.temporary.name) / "unsafe.csv"
        with self.assertRaises(ExportError):
            export_month(unsafe_month, destination)
        self.assertFalse(destination.exists())

        self.sql.execute(
            "UPDATE day_entries SET special_day = ? WHERE work_date = ?",
            ("stored\x00control", day.work_date.isoformat()),
        )
        with self.assertRaises(StorageCorrupt):
            self.repository.load_month(2024, 2)

    def test_sqlite_and_legacy_write_boundaries_are_isolated(self):
        root = Path(__file__).resolve().parents[1] / "znactime"
        sqlite_importers = []
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "import sqlite3" in text or "from sqlite3" in text:
                sqlite_importers.append(path.relative_to(root).as_posix())
        self.assertTrue(sqlite_importers)
        self.assertTrue(all(item.startswith("storage/sqlite/") for item in sqlite_importers))

        app_text = (root / "ui" / "qt" / "app.py").read_text(encoding="utf-8")
        model_text = (root / "ui" / "qt" / "model.py").read_text(encoding="utf-8")
        self.assertNotIn("csv_store", app_text)
        self.assertNotIn("csv_store", model_text)
        self.assertNotIn("workday_timer/", app_text)
        for path in (root / "storage" / "sqlite").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(text.upper(), r"SELECT\s+(?:\w+\.)?\*")
        for path in root.rglob("*.py"):
            self.assertNotRegex(
                path.read_text(encoding="utf-8"),
                r"(?m)^\s*assert\s",
            )


if __name__ == "__main__":
    unittest.main()
