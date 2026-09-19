import calendar
import csv
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from znactime.storage.legacy_csv_import import (
    LegacyImportCancelled,
    preflight_legacy_data,
)
from znactime.storage.sqlite.bootstrap import migrate_legacy_database
from znactime.storage.sqlite.legacy_verify import verify_legacy_import
from znactime.storage.sqlite.repository import SQLiteRepository


class LegacyImportVerificationTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "data"
        self.year_dir = self.root / "2024"
        self.year_dir.mkdir(parents=True)
        self.database = Path(self.temporary.name) / "app-data" / "znactime.db"

    def tearDown(self):
        self.temporary.cleanup()

    def _write_month(self, month, *, opening=0, closed=False):
        path = self.year_dir / f"2024_tmp_{month:02}.csv"
        running = opening
        rows = [["#znacTime-csv", "2"]]
        for day_number in range(1, calendar.monthrange(2024, month)[1] + 1):
            work_date = date(2024, month, day_number).strftime("%d.%m.%Y")
            if day_number == 1:
                start, end, interruption, daily = "08:00", "17:00", "00:30", 30
                running += daily
            else:
                start, end, interruption, daily = "00:00", "00:00", "00:00", 0
            rows.append(
                [
                    work_date,
                    "Normal day",
                    start,
                    end,
                    interruption,
                    f"{daily // 60:02d}:{daily % 60:02d}",
                    f"{running // 60:02d}:{running % 60:02d}",
                ]
            )
        with path.open("w", newline="", encoding="utf-8") as stream:
            csv.writer(stream).writerows(rows)
        if closed:
            (self.year_dir / f"closed_{month:02}.flag").write_text("", encoding="utf-8")

    def _import(self):
        preflight = preflight_legacy_data(self.root)
        repository = migrate_legacy_database(preflight, self.database)
        repository.close()

    def test_exact_open_and_closed_import_passes_field_verification(self):
        self._write_month(1, closed=True)
        self._write_month(2, opening=30)
        self._import()

        report = verify_legacy_import(self.root, self.database)

        self.assertTrue(report.structurally_valid)
        self.assertTrue(report.exact)
        self.assertEqual(report.source_days_checked, 60)
        self.assertEqual(report.exact_input_days, 60)
        self.assertEqual(report.database_closed_result_count, 31)

    def test_local_edit_is_reported_as_difference_not_import_loss(self):
        self._write_month(2)
        self._import()

        repository = SQLiteRepository(self.database)
        try:
            month = repository.load_month(2024, 2)
            repository.update_day(
                month.days[0].work_date,
                expected_revision=month.days[0].revision,
                start_minute=420,
                fields=frozenset(("start_minute",)),
            )
        finally:
            repository.close()

        report = verify_legacy_import(self.root, self.database)

        self.assertTrue(report.structurally_valid)
        self.assertFalse(report.exact)
        self.assertEqual(report.input_difference_days, 1)
        self.assertTrue(
            any(issue.field == "start_minute" for issue in report.local_differences)
        )
        self.assertTrue(report.derived_differences)

    def test_month_state_parity_is_reported_separately_from_day_inputs(self):
        self._write_month(2)
        self._import()

        connection = sqlite3.connect(self.database)
        try:
            connection.execute(
                """
                UPDATE months
                SET opening_balance_minutes = 60,
                    updated_at = '2024-03-01T00:00:00Z',
                    revision = revision + 1
                WHERE year = 2024 AND month = 2
                """
            )
            connection.commit()
        finally:
            connection.close()

        report = verify_legacy_import(self.root, self.database)

        self.assertTrue(report.structurally_valid)
        self.assertEqual(report.exact_input_days, 29)
        self.assertEqual(report.input_difference_days, 0)
        self.assertEqual(report.exact_input_months, 0)
        self.assertEqual(report.input_difference_months, 1)
        self.assertTrue(
            any(
                issue.location == "2024-02"
                and issue.field == "opening_balance_minutes"
                for issue in report.local_differences
            )
        )

    def test_missing_source_day_is_a_structural_error(self):
        self._write_month(2)
        self._import()

        connection = sqlite3.connect(self.database)
        try:
            connection.execute("DELETE FROM day_entries WHERE work_date = '2024-02-02'")
            connection.commit()
        finally:
            connection.close()

        report = verify_legacy_import(self.root, self.database)

        self.assertFalse(report.structurally_valid)
        self.assertTrue(
            any(
                issue.location == "2024-02-02" and issue.field == "day"
                for issue in report.errors
            )
        )

    def test_result_snapshot_on_open_month_is_a_structural_error(self):
        self._write_month(2)
        self._import()

        connection = sqlite3.connect(self.database)
        try:
            day_id = connection.execute(
                "SELECT id FROM day_entries WHERE work_date = '2024-02-01'"
            ).fetchone()[0]
            connection.execute(
                """
                INSERT INTO closed_day_results(
                    day_entry_id, daily_overtime_minutes, running_balance_minutes
                ) VALUES (?, 30, 30)
                """,
                (day_id,),
            )
            connection.commit()
        finally:
            connection.close()

        report = verify_legacy_import(self.root, self.database)

        self.assertFalse(report.structurally_valid)
        self.assertTrue(
            any(
                issue.location == "2024-02-01"
                and issue.field == "closed_day_result"
                for issue in report.errors
            )
        )

    def test_changed_csv_snapshot_does_not_match_recorded_import(self):
        self._write_month(2)
        self._import()
        source_file = self.year_dir / "2024_tmp_02.csv"
        source_file.write_text(
            source_file.read_text(encoding="utf-8").replace(
                "01.02.2024,Normal day,08:00", "01.02.2024,Vacation,08:00"
            ),
            encoding="utf-8",
        )

        report = verify_legacy_import(self.root, self.database)

        self.assertFalse(report.structurally_valid)
        self.assertTrue(
            any(
                issue.location == "legacy_imports"
                and issue.field == "source_fingerprint"
                for issue in report.errors
            )
        )

    def test_database_with_more_than_one_dataset_is_rejected(self):
        self._write_month(2)
        self._import()

        connection = sqlite3.connect(self.database)
        try:
            connection.execute(
                """
                INSERT INTO datasets(public_id, created_at)
                VALUES ('00000000-0000-4000-8000-000000000001', '2024-01-01T00:00:00Z')
                """
            )
            connection.commit()
        finally:
            connection.close()

        report = verify_legacy_import(self.root, self.database)

        self.assertFalse(report.structurally_valid)
        self.assertTrue(
            any(issue.field == "dataset_count" for issue in report.errors)
        )

    def test_database_with_unsupported_version_is_rejected(self):
        self._write_month(2)
        self._import()

        connection = sqlite3.connect(self.database)
        try:
            connection.execute("PRAGMA user_version = 3")
            connection.commit()
        finally:
            connection.close()

        report = verify_legacy_import(self.root, self.database)

        self.assertFalse(report.structurally_valid)
        self.assertTrue(
            any(issue.field == "schema_version" for issue in report.errors)
        )

    def test_database_with_incomplete_migration_history_is_rejected(self):
        self._write_month(2)
        self._import()

        connection = sqlite3.connect(self.database)
        try:
            connection.execute(
                """
                INSERT INTO schema_migrations(version, applied_at, app_version)
                VALUES (2, '2024-01-01T00:00:00Z', 'test')
                """
            )
            connection.commit()
        finally:
            connection.close()

        report = verify_legacy_import(self.root, self.database)

        self.assertFalse(report.structurally_valid)
        self.assertTrue(
            any(issue.field == "migration_history" for issue in report.errors)
        )

    def test_database_with_missing_schema_object_is_rejected(self):
        self._write_month(2)
        self._import()

        connection = sqlite3.connect(self.database)
        try:
            connection.execute("DROP TRIGGER dataset_identity_immutable")
            connection.commit()
        finally:
            connection.close()

        report = verify_legacy_import(self.root, self.database)

        self.assertFalse(report.structurally_valid)
        self.assertTrue(
            any(issue.field == "schema_definitions" for issue in report.errors)
        )

    def test_verification_can_be_cancelled_during_database_checks(self):
        self._write_month(2)
        self._import()
        cancel = False

        def progress(phase, _completed, _total):
            nonlocal cancel
            if phase == "Checking SQLite integrity":
                cancel = True

        with self.assertRaises(LegacyImportCancelled):
            verify_legacy_import(
                self.root,
                self.database,
                progress=progress,
                cancelled=lambda: cancel,
            )


if __name__ == "__main__":
    unittest.main()
