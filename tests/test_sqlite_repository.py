import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from znactime.core.models import BreakRecord
from znactime.storage.errors import ClosedPeriodError, StorageConflict, StorageCorrupt
from znactime.storage.csv_export import export_month
from znactime.storage.legacy_csv_import import preflight_legacy_data
from znactime.storage.legacy_csv_import import LegacyImportCancelled
from znactime.storage.sqlite.repository import SQLiteRepository


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

    def test_create_and_calendar_month_round_trip(self):
        month = self.repository.get_or_create_month(2024, 2)

        self.assertEqual(len(month.days), 29)
        self.assertEqual(month.days[0].work_date, date(2024, 2, 1))
        self.assertEqual(month.days[-1].work_date, date(2024, 2, 29))
        self.assertEqual(month.days[0].expected_work_minutes, 480)
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

    def test_close_is_atomic_immutable_and_carries_to_successor(self):
        june = self.repository.get_or_create_month(2024, 6)
        july = self.repository.get_or_create_month(2024, 7)
        first = june.days[0]
        self.repository.update_day(
            first.work_date,
            expected_revision=first.revision,
            start_minute=480,
            end_minute=1020,
            break_duration_minutes=30,
            fields=frozenset(("start_minute", "end_minute", "break_duration_minutes")),
        )

        closed = self.repository.close_month(2024, 6, expected_revision=june.revision)
        self.assertEqual(closed.status, "closed")
        self.assertEqual(closed.closing_balance_minutes, 30)
        self.assertEqual(self.repository.load_month(2024, 7).opening_balance_minutes, 30)
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
        with self.assertRaises(sqlite3.IntegrityError):
            self.sql.execute(
                "UPDATE months SET status = 'open' WHERE year = 2024 AND month = 6"
            )
        with self.assertRaises(ClosedPeriodError):
            self.repository.update_day(
                first.work_date,
                expected_revision=first.revision + 1,
                special_day="Changed",
                fields=frozenset(("special_day",)),
            )

    def test_later_closed_month_does_not_freeze_unrelated_open_history(self):
        january = self.repository.get_or_create_month(2024, 1)
        february = self.repository.get_or_create_month(2024, 2)
        self.repository.close_month(2024, 2, expected_revision=february.revision)

        changed = self.repository.update_day(
            january.days[0].work_date,
            expected_revision=january.days[0].revision,
            special_day="Corrected",
            fields=frozenset(("special_day",)),
        )

        self.assertEqual(changed.special_day, "Corrected")
        with self.assertRaises(ClosedPeriodError):
            self.repository.close_month(2024, 1, expected_revision=january.revision)

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

    def test_schema_has_no_independent_active_workday_state(self):
        table = self.sql.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'active_workday'"
        ).fetchone()

        self.assertIsNone(table)

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
                3,
            )
        finally:
            upgraded.close()

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
        self.repository.replace_work_schedule(
            effective_from=date(2024, 6, 1),
            effective_to=None,
            weekday_minutes=(420, 420, 420, 420, 420, 0, 0),
        )
        changed = self.repository.load_month(2024, 6)
        self.assertEqual(changed.days[0].expected_work_minutes, 300)
        self.assertEqual(changed.days[1].expected_work_minutes, 0)
        self.assertEqual(changed.days[3].expected_work_minutes, 420)

    def test_backdated_schedule_is_bounded_by_the_following_period(self):
        self.repository.replace_work_schedule(
            effective_from=date(2024, 6, 1),
            effective_to=None,
            weekday_minutes=(420, 420, 420, 420, 420, 0, 0),
        )

        may = self.repository.replace_work_schedule(
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


if __name__ == "__main__":
    unittest.main()
