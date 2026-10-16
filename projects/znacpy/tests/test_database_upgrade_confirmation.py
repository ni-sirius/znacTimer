import os
import sqlite3
import tempfile
import unittest
import uuid
from contextlib import closing, contextmanager
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from znactime.storage.errors import StorageUnavailable
from znactime.storage.sqlite.bootstrap import (
    FailedMigrationRecovery,
    SchemaUpgrade,
    inspect_schema_upgrade,
)
from znactime.storage.sqlite.repository import SQLiteRepository
from znactime.storage.sqlite.schema import SCHEMA_VERSION, SCHEMA_V6_SQL
from znactime.ui.qt.first_launch import open_or_initialize_repository


class DatabaseUpgradeConfirmationTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = Path(self.temporary.name) / "znactime.db"
        with closing(sqlite3.connect(self.database)) as sql, sql:
            sql.executescript(SCHEMA_V6_SQL)
            sql.execute("INSERT INTO schema_migrations VALUES (6, 'test', 'old app')")
            sql.execute("PRAGMA user_version = 6")
            dataset = sql.execute(
                "INSERT INTO datasets(public_id, created_at) VALUES (?, 'test')",
                (str(uuid.uuid4()),),
            ).lastrowid
            month = sql.execute(
                "INSERT INTO months(dataset_id, year, month, status, "
                "opening_balance_minutes, created_at, updated_at) "
                "VALUES (?, 2024, 6, 'open', 0, 'test', 'test')",
                (dataset,),
            ).lastrowid
            sql.execute(
                "INSERT INTO day_entries(month_id, work_date, special_day, "
                "start_minute, end_minute, break_duration_minutes, "
                "expected_work_minutes, created_at, updated_at) "
                "VALUES (?, '2024-06-03', 'Normal day', 480, 1020, 30, 480, 'test', 'test')",
                (month,),
            )

    @contextmanager
    def dialog(self, selected_label=None):
        dialog = Mock()
        buttons = {}

        def button(label, _parent):
            buttons[label] = Mock(name=label)
            return buttons[label]

        def select():
            dialog.clickedButton.return_value = buttons.get(selected_label)

        dialog.exec.side_effect = select
        with (
            patch("znactime.ui.qt.first_launch.QMessageBox", return_value=dialog),
            patch("znactime.ui.qt.first_launch.QPushButton", side_effect=button),
        ):
            yield dialog, buttons

    def test_upgrade_inspection_is_read_only_and_reports_both_versions(self):
        before = self.database.read_bytes()
        self.assertEqual(inspect_schema_upgrade(self.database), SchemaUpgrade(6, SCHEMA_VERSION))
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(list(self.database.parent.iterdir()), [self.database])

    def test_missing_database_is_not_created_by_inspection(self):
        missing = self.database.parent / "missing.db"
        with self.assertRaises(StorageUnavailable):
            inspect_schema_upgrade(missing)
        self.assertFalse(missing.exists())

    def test_exit_and_window_close_preserve_database_without_opening_for_writing(self):
        for selected in ("Exit application", None):
            with self.subTest(selected=selected):
                before = self.database.read_bytes()
                with self.dialog(selected), patch(
                    "znactime.ui.qt.first_launch.SQLiteRepository",
                ) as repository:
                    self.assertIsNone(open_or_initialize_repository(target=self.database))
                repository.assert_not_called()
                self.assertEqual(self.database.read_bytes(), before)
                self.assertFalse((self.database.parent / "recovery").exists())

    def test_dialog_explains_irreversibility_and_defaults_to_exit(self):
        with self.dialog() as (dialog, buttons):
            self.assertIsNone(open_or_initialize_repository(target=self.database))
        dialog.setWindowTitle.assert_called_once_with("Database upgrade required")
        text = dialog.setText.call_args.args[0]
        self.assertIn("version 6", text)
        self.assertIn(f"version {SCHEMA_VERSION}", text)
        explanation = dialog.setInformativeText.call_args.args[0]
        self.assertIn("irreversible", explanation)
        self.assertIn("Older app versions", explanation)
        self.assertIn("unchanged", explanation)
        dialog.setDefaultButton.assert_called_once_with(buttons["Exit application"])
        dialog.setEscapeButton.assert_called_once_with(buttons["Exit application"])

    def test_accepting_upgrades_and_preserves_existing_records(self):
        with self.dialog("Upgrade database"):
            repository = open_or_initialize_repository(target=self.database)
        self.assertIsNotNone(repository)
        try:
            self.assertIsNone(inspect_schema_upgrade(self.database))
            self.assertEqual(repository.load_month(2024, 6).days[0].start_minute, 480)
            self.assertEqual(repository.load_month(2024, 6).days[0].end_minute, 1020)
        finally:
            repository.close()
        with closing(sqlite3.connect(self.database)) as sql:
            self.assertEqual(sql.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)

    def test_current_database_opens_without_upgrade_prompt(self):
        SQLiteRepository(self.database).close()
        with patch("znactime.ui.qt.first_launch.QMessageBox") as dialog:
            repository = open_or_initialize_repository(target=self.database)
        try:
            self.assertIsNotNone(repository)
            dialog.assert_not_called()
        finally:
            repository.close()

    def test_declining_preserves_wal_records_and_journal_mode(self):
        with closing(sqlite3.connect(self.database, isolation_level=None)) as writer:
            writer.execute("PRAGMA journal_mode = WAL")
            writer.execute("PRAGMA wal_autocheckpoint = 0")
            writer.execute("UPDATE day_entries SET start_minute = 490")
            before = self.database.read_bytes()
            wal = Path(str(self.database) + "-wal")
            before_wal = wal.read_bytes()
            with self.dialog("Exit application"):
                self.assertIsNone(open_or_initialize_repository(target=self.database))
            self.assertEqual(self.database.read_bytes(), before)
            self.assertEqual(wal.read_bytes(), before_wal)
            self.assertEqual(writer.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            self.assertEqual(writer.execute("SELECT start_minute FROM day_entries").fetchone()[0], 490)

    def test_pending_recovery_requires_consent_before_restoring_or_upgrading(self):
        backup = self.database.parent / "recovery" / "pre-upgrade" / self.database.name
        backup.parent.mkdir(parents=True)
        backup.write_bytes(self.database.read_bytes())
        self.database.write_bytes(b"interrupted recovery")
        recovery = FailedMigrationRecovery(backup, "signature", "test", "interrupted")
        with (
            self.dialog("Exit application") as (dialog, _buttons),
            patch("znactime.ui.qt.first_launch.failed_migration_recovery", return_value=recovery),
            patch("znactime.ui.qt.first_launch.recover_failed_schema_migration") as restore,
        ):
            self.assertIsNone(open_or_initialize_repository(target=self.database))
        restore.assert_not_called()
        self.assertEqual(self.database.read_bytes(), b"interrupted recovery")
        self.assertEqual(inspect_schema_upgrade(backup), SchemaUpgrade(6, SCHEMA_VERSION))
        self.assertIn("restored and then upgraded", dialog.setInformativeText.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
