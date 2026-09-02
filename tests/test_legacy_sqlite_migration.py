import calendar
import csv
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from znactime.storage.errors import ClosedPeriodError
from znactime.storage.legacy_csv_import import (
    LegacyImportCancelled,
    preflight_legacy_data,
)
from znactime.storage.sqlite.bootstrap import (
    BootstrapState,
    inspect_bootstrap,
    migrate_legacy_database,
)
from znactime.storage.sqlite.repository import SQLiteRepository


class LegacySQLiteMigrationTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "data"
        self.root.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def _write_month(
        self, year, month, *, closed=False, invalid_start=None, opening_minutes=0
    ):
        year_dir = self.root / str(year)
        year_dir.mkdir(exist_ok=True)
        path = year_dir / f"{year}_tmp_{month:02}.csv"
        rows = [["#znacTime-csv", "2"]]
        def hhmm(minutes):
            return f"{minutes // 60:02d}:{minutes % 60:02d}"

        running = hhmm(opening_minutes)
        for day_number in range(1, calendar.monthrange(year, month)[1] + 1):
            current = date(year, month, day_number).strftime("%d.%m.%Y")
            if day_number == 1:
                start = invalid_start or "08:00"
                end = "17:00"
                interruption = "00:30"
                daily = "00:30"
                running = hhmm(opening_minutes + 30)
            else:
                start = "00:00"
                end = "00:00"
                interruption = "00:00"
                daily = "00:00"
            rows.append([current, "Normal day", start, end, interruption, daily, running])
        with path.open("w", newline="", encoding="utf-8") as stream:
            csv.writer(stream).writerows(rows)
        if closed:
            (year_dir / f"closed_{month:02}.flag").write_text("", encoding="utf-8")
        return path

    def test_preflight_is_lossless_and_reports_legacy_midnight_ambiguity(self):
        self._write_month(2024, 2)
        result = preflight_legacy_data(self.root)

        self.assertFalse(result.blocking_errors)
        self.assertEqual(len(result.months), 1)
        self.assertEqual(len(result.months[0].days), 29)
        self.assertTrue(any("not midnight" in issue.message for issue in result.warnings))
        self.assertEqual(result.months[0].days[1].start_minute, None)

    def test_preflight_decodes_v3_safety_escape_but_leaves_v2_unchanged(self):
        year_dir = self.root / "2024"
        year_dir.mkdir()
        v2 = year_dir / "2024_tmp_06.csv"
        v3 = year_dir / "2024_tmp_08.csv"
        with v2.open("w", newline="", encoding="utf-8") as stream:
            csv.writer(stream).writerows(
                [
                    ["#znacTime-csv", "2"],
                    [
                        "17.06.2024", "'=legacy literal", "08:00", "17:00",
                        "00:00", "00:00", "00:00",
                    ],
                ]
            )
        with v3.open("w", newline="", encoding="utf-8") as stream:
            csv.writer(stream).writerows(
                [
                    ["#znacTime-csv", "3"],
                    [
                        "17.08.2024", "'=1+1", "08:00", "17:00",
                        "00:00", "00:00", "00:00",
                    ],
                    [
                        "18.08.2024", "''=literal apostrophe", "08:00", "17:00",
                        "00:00", "00:00", "00:00",
                    ],
                ]
            )
        original_v2 = v2.read_bytes()
        original_v3 = v3.read_bytes()

        result = preflight_legacy_data(self.root)

        self.assertFalse(result.blocking_errors)
        self.assertEqual(result.months[0].days[0].special_day, "'=legacy literal")
        self.assertEqual(result.months[1].days[0].special_day, "=1+1")
        self.assertEqual(
            result.months[1].days[1].special_day,
            "'=literal apostrophe",
        )
        self.assertEqual(v2.read_bytes(), original_v2)
        self.assertEqual(v3.read_bytes(), original_v3)

    def test_invalid_value_is_blocking_instead_of_becoming_zero(self):
        self._write_month(2024, 2, invalid_start="99:99")
        result = preflight_legacy_data(self.root)

        self.assertTrue(result.blocking_errors)
        self.assertTrue(any("Invalid start" in issue.message for issue in result.blocking_errors))

    def test_closed_then_open_month_migrates_without_touching_source(self):
        january = self._write_month(2024, 1, closed=True)
        self._write_month(2024, 2, opening_minutes=30)
        original = january.read_bytes()
        preflight = preflight_legacy_data(self.root)
        target = Path(self.temporary.name) / "app-data" / "znactime.db"

        repository = migrate_legacy_database(preflight, target)
        try:
            self.assertEqual(inspect_bootstrap(target).state, BootstrapState.READY)
            self.assertTrue(repository.is_month_closed(2024, 1))
            self.assertEqual(repository.load_month(2024, 1).closing_balance_minutes, 30)
            self.assertEqual(repository.load_month(2024, 2).opening_balance_minutes, 30)
            connection = sqlite3.connect(target)
            try:
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM legacy_imports").fetchone()[0],
                    1,
                )
            finally:
                connection.close()
            self.assertFalse(target.with_name(target.name + ".migrating").exists())
        finally:
            repository.close()
        self.assertEqual(january.read_bytes(), original)

    def test_closed_after_open_chain_is_preserved_with_warning(self):
        self._write_month(2024, 1, closed=False)
        self._write_month(2024, 2, closed=True)
        result = preflight_legacy_data(self.root)

        self.assertFalse(result.blocking_errors)
        self.assertTrue(
            any("Closed month follows" in issue.message for issue in result.warnings)
        )
        target = Path(self.temporary.name) / "app-data" / "znactime.db"
        repository = migrate_legacy_database(result, target)
        try:
            january = repository.load_month(2024, 1)
            february = repository.load_month(2024, 2)
            self.assertEqual(january.status, "open")
            self.assertEqual(february.status, "closed")
            changed = repository.update_day(
                january.days[0].work_date,
                expected_revision=january.days[0].revision,
                special_day="Corrected",
                fields=frozenset(("special_day",)),
            )
            self.assertEqual(changed.special_day, "Corrected")
            with self.assertRaises(ClosedPeriodError):
                repository.close_month(2024, 1, expected_revision=january.revision)
        finally:
            repository.close()

    def test_partial_month_import_creates_missing_blank_calendar_days(self):
        year_dir = self.root / "2024"
        year_dir.mkdir()
        path = year_dir / "2024_tmp_06.csv"
        with path.open("w", newline="", encoding="utf-8") as stream:
            csv.writer(stream).writerows(
                [
                    ["#znacTime-csv", "2"],
                    [
                        "17.06.2024", "Normal day", "08:00", "00:00",
                        "17:00-18:00", "00:00", "00:00",
                    ],
                ]
            )

        result = preflight_legacy_data(self.root)

        self.assertFalse(result.blocking_errors)
        self.assertTrue(any("blank rows will be created" in item.message for item in result.warnings))
        target = Path(self.temporary.name) / "app-data" / "znactime.db"
        repository = migrate_legacy_database(result, target)
        try:
            month = repository.load_month(2024, 6)
            self.assertEqual(len(month.days), 30)
            migrated = next(item for item in month.days if item.work_date == date(2024, 6, 17))
            self.assertEqual(migrated.start_minute, 480)
            blank = next(item for item in month.days if item.work_date == date(2024, 6, 1))
            self.assertIsNone(blank.start_minute)
        finally:
            repository.close()

    def test_invalid_closed_workday_is_imported_as_immutable_snapshot(self):
        self._write_month(2024, 2, closed=True, invalid_start="23:00")
        result = preflight_legacy_data(self.root)

        self.assertFalse(result.blocking_errors)
        self.assertTrue(any("reversed workday" in item.message for item in result.warnings))
        target = Path(self.temporary.name) / "app-data" / "znactime.db"
        repository = migrate_legacy_database(result, target)
        try:
            month = repository.load_month(2024, 2)
            self.assertEqual(month.status, "closed")
            self.assertEqual(month.days[0].start_minute, 23 * 60)
            self.assertEqual(month.days[0].end_minute, 17 * 60)
            self.assertEqual(month.days[0].daily_overtime_minutes, 30)
            with self.assertRaises(ClosedPeriodError):
                repository.update_day(
                    month.days[0].work_date,
                    expected_revision=month.days[0].revision,
                    special_day="Changed",
                    fields=frozenset(("special_day",)),
                )
        finally:
            repository.close()

    def test_orphan_closed_flag_is_blocking(self):
        year_dir = self.root / "2024"
        year_dir.mkdir()
        (year_dir / "closed_02.flag").write_text("", encoding="utf-8")

        result = preflight_legacy_data(self.root)

        self.assertTrue(
            any("no matching monthly CSV" in issue.message for issue in result.blocking_errors)
        )

    def test_invalid_calendar_month_file_is_reported_without_crashing(self):
        year_dir = self.root / "2024"
        year_dir.mkdir()
        (year_dir / "2024_tmp_99.csv").write_text("", encoding="utf-8")

        result = preflight_legacy_data(self.root)

        self.assertTrue(
            any("Invalid year or month" in issue.message for issue in result.blocking_errors)
        )

    def test_preflight_ignores_unrecognized_and_nested_files(self):
        month = self._write_month(2024, 2)
        before = preflight_legacy_data(self.root)
        (self.root / "unrelated.bin").write_bytes(b"not part of the import")
        nested = self.root / "archive" / "2024"
        nested.mkdir(parents=True)
        (nested / month.name).write_bytes(month.read_bytes())

        after = preflight_legacy_data(self.root)

        self.assertEqual(after.file_count, 1)
        self.assertEqual(after.manifest_digest, before.manifest_digest)

    def test_preflight_enforces_file_total_row_and_row_size_limits(self):
        month = self._write_month(2024, 2)

        with patch(
            "znactime.storage.legacy_csv_import.MAX_CSV_BYTES",
            month.stat().st_size - 1,
        ), self.assertRaisesRegex(ValueError, "CSV exceeds"):
            preflight_legacy_data(self.root)

        with patch(
            "znactime.storage.legacy_csv_import.MAX_TOTAL_BYTES",
            month.stat().st_size - 1,
        ), self.assertRaisesRegex(ValueError, "total limit"):
            preflight_legacy_data(self.root)

        with patch(
            "znactime.storage.legacy_csv_import.MAX_CSV_ROWS",
            2,
        ), self.assertRaisesRegex(ValueError, "row limit"):
            preflight_legacy_data(self.root)

        with patch(
            "znactime.storage.legacy_csv_import.MAX_CSV_ROW_BYTES",
            12,
        ), self.assertRaisesRegex(ValueError, "CSV row exceeds"):
            preflight_legacy_data(self.root)

    def test_preflight_enforces_recognized_file_limit(self):
        self._write_month(2024, 2, closed=True)

        with patch(
            "znactime.storage.legacy_csv_import.MAX_RECOGNIZED_FILES",
            1,
        ), self.assertRaisesRegex(ValueError, "file limit"):
            preflight_legacy_data(self.root)

    def test_preflight_rejects_recognized_symlink(self):
        target = self._write_month(2024, 2)
        linked = target.parent / "2024_tmp_03.csv"
        try:
            linked.symlink_to(target)
        except OSError as error:
            self.skipTest(f"Symlinks are unavailable in this environment: {error}")

        with self.assertRaisesRegex(ValueError, "does not allow links"):
            preflight_legacy_data(self.root)

    def test_preflight_supports_progress_and_cancellation(self):
        self._write_month(2024, 2)
        updates = []

        preflight_legacy_data(
            self.root,
            progress=lambda phase, completed, total: updates.append(
                (phase, completed, total)
            ),
        )

        self.assertTrue(any(item[0] == "Hashing legacy files" for item in updates))
        self.assertTrue(any(item[0] == "Parsing legacy months" for item in updates))
        with self.assertRaises(LegacyImportCancelled):
            preflight_legacy_data(self.root, cancelled=lambda: True)

    def test_merge_keeps_local_day_and_imports_untouched_day(self):
        path = self._write_month(2024, 2)
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.reader(stream))
        rows[2][2:7] = ["09:00", "18:00", "00:30", "00:30", "01:00"]
        with path.open("w", newline="", encoding="utf-8") as stream:
            csv.writer(stream).writerows(rows)
        preflight = preflight_legacy_data(self.root)
        target = Path(self.temporary.name) / "app-data" / "znactime.db"
        repository = SQLiteRepository.create(target)
        try:
            month = repository.get_or_create_month(2024, 2)
            local = repository.update_day(
                month.days[0].work_date,
                expected_revision=month.days[0].revision,
                start_minute=420,
                end_minute=900,
                fields=frozenset(("start_minute", "end_minute")),
            )

            result = repository.merge_legacy(preflight)

            merged = repository.load_month(2024, 2)
            self.assertEqual(merged.days[0].start_minute, 420)
            self.assertEqual(merged.days[0].end_minute, 900)
            self.assertEqual(merged.days[0].revision, local.revision)
            self.assertEqual(merged.days[1].start_minute, 540)
            self.assertEqual(merged.days[1].end_minute, 1080)
            self.assertEqual(result.days_kept_current, 1)
            self.assertEqual(result.days_imported, 1)
            self.assertEqual(result.months_merged, 1)

            repeated = repository.merge_legacy(preflight)
            self.assertTrue(repeated.already_imported)
            self.assertEqual(repeated.days_imported, 0)
        finally:
            repository.close()

    def test_schedule_only_revision_does_not_block_legacy_day_import(self):
        self._write_month(2024, 2)
        preflight = preflight_legacy_data(self.root)
        target = Path(self.temporary.name) / "app-data" / "znactime.db"
        repository = SQLiteRepository.create(target)
        try:
            repository.get_or_create_month(2024, 2)
            repository.replace_work_schedule(
                effective_from=date(2024, 2, 1),
                effective_to=None,
                weekday_minutes=(420, 420, 420, 420, 420, 0, 0),
            )
            metadata = repository._connection.execute(
                """
                SELECT revision, local_input_revision FROM day_entries
                WHERE work_date = '2024-02-01'
                """
            ).fetchone()
            self.assertEqual(tuple(metadata), (2, 0))

            result = repository.merge_legacy(preflight)

            imported = repository.load_month(2024, 2).days[0]
            self.assertEqual(imported.start_minute, 480)
            self.assertEqual(imported.end_minute, 1020)
            self.assertEqual(result.days_imported, 1)
            self.assertEqual(result.days_kept_current, 0)
        finally:
            repository.close()

    def test_user_cleared_day_remains_authoritative_during_legacy_merge(self):
        self._write_month(2024, 2)
        preflight = preflight_legacy_data(self.root)
        target = Path(self.temporary.name) / "app-data" / "znactime.db"
        repository = SQLiteRepository.create(target)
        try:
            day = repository.get_or_create_month(2024, 2).days[0]
            changed = repository.update_day(
                day.work_date,
                expected_revision=day.revision,
                special_day="Vacation",
                fields=frozenset(("special_day",)),
            )
            repository.update_day(
                day.work_date,
                expected_revision=changed.revision,
                special_day="Normal day",
                fields=frozenset(("special_day",)),
            )

            result = repository.merge_legacy(preflight)

            preserved = repository.load_month(2024, 2).days[0]
            self.assertEqual(preserved.special_day, "Normal day")
            self.assertIsNone(preserved.start_minute)
            self.assertIsNone(preserved.end_minute)
            self.assertEqual(result.days_kept_current, 1)
            self.assertEqual(result.days_imported, 0)
        finally:
            repository.close()

    def test_cancelled_merge_rolls_back_all_database_changes(self):
        self._write_month(2024, 2)
        preflight = preflight_legacy_data(self.root)
        target = Path(self.temporary.name) / "app-data" / "znactime.db"
        repository = SQLiteRepository.create(target)
        checks = 0

        def cancelled():
            nonlocal checks
            checks += 1
            return checks > 2

        try:
            with self.assertRaises(LegacyImportCancelled):
                repository.merge_legacy(preflight, cancelled=cancelled)

            self.assertEqual(
                repository._connection.execute("SELECT COUNT(*) FROM months").fetchone()[0],
                0,
            )
            self.assertEqual(
                repository._connection.execute(
                    "SELECT COUNT(*) FROM legacy_imports"
                ).fetchone()[0],
                0,
            )
        finally:
            repository.close()

    def test_cancelled_first_launch_migration_removes_staging_database(self):
        self._write_month(2024, 2)
        preflight = preflight_legacy_data(self.root)
        target = Path(self.temporary.name) / "app-data" / "znactime.db"

        with self.assertRaises(LegacyImportCancelled):
            migrate_legacy_database(
                preflight,
                target,
                cancelled=lambda: True,
            )

        self.assertFalse(target.exists())
        self.assertFalse(target.with_name(target.name + ".migrating").exists())
        self.assertFalse(
            target.with_name(target.name + ".migrating-wal").exists()
        )
        self.assertFalse(
            target.with_name(target.name + ".migrating-shm").exists()
        )

    def test_closed_csv_with_local_conflict_stays_open(self):
        path = self._write_month(2024, 2, closed=True)
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.reader(stream))
        rows[2][2:7] = ["09:00", "18:00", "00:30", "00:30", "01:00"]
        with path.open("w", newline="", encoding="utf-8") as stream:
            csv.writer(stream).writerows(rows)
        preflight = preflight_legacy_data(self.root)
        target = Path(self.temporary.name) / "app-data" / "znactime.db"
        repository = SQLiteRepository.create(target)
        try:
            month = repository.get_or_create_month(2024, 2)
            repository.update_day(
                month.days[0].work_date,
                expected_revision=month.days[0].revision,
                special_day="Local correction",
                fields=frozenset(("special_day",)),
            )

            result = repository.merge_legacy(preflight)

            merged = repository.load_month(2024, 2)
            self.assertEqual(merged.status, "open")
            self.assertEqual(merged.days[0].special_day, "Local correction")
            self.assertEqual(merged.days[1].start_minute, 540)
            self.assertEqual(result.closures_kept_open, 1)
            self.assertEqual(result.months_closed, 0)
            connection = sqlite3.connect(target)
            try:
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM closed_day_results").fetchone()[0],
                    0,
                )
            finally:
                connection.close()
        finally:
            repository.close()

    def test_merge_never_changes_a_closed_local_month(self):
        self._write_month(2024, 2)
        preflight = preflight_legacy_data(self.root)
        target = Path(self.temporary.name) / "app-data" / "znactime.db"
        repository = SQLiteRepository.create(target)
        try:
            month = repository.get_or_create_month(2024, 2)
            closed = repository.close_month(2024, 2, expected_revision=month.revision)

            result = repository.merge_legacy(preflight)

            preserved = repository.load_month(2024, 2)
            self.assertEqual(preserved.status, "closed")
            self.assertEqual(preserved.revision, closed.revision)
            self.assertIsNone(preserved.days[0].start_minute)
            self.assertGreaterEqual(result.days_kept_current, 1)
            self.assertEqual(result.days_imported, 0)
        finally:
            repository.close()


if __name__ == "__main__":
    unittest.main()
