import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from znactime.storage.errors import DatabaseVersionTooNew, StorageConflict, StorageUnavailable
from znactime.storage.legacy_csv_import import LegacyImportCancelled
from znactime.storage.sqlite.backup import backup_connection
from znactime.storage.sqlite.bootstrap import replace_newer_database
from znactime.storage.sqlite.repository import SQLiteRepository
from znactime.storage.sqlite.schema import SCHEMA_VERSION
from znactime.ui.qt.first_launch import (
    NewerDatabaseChoice,
    _show_newer_database_dialog,
    open_or_initialize_repository,
)


class NewerDatabaseResetTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.database = self.root / "znactime.db"
        self.backup = self.root / "backups" / "saved.db"
        self.version = SCHEMA_VERSION + 2
        repository = SQLiteRepository.create(self.database)
        repository.get_or_create_month(2024, 2)
        repository.close()
        with closing(sqlite3.connect(self.database)) as sql, sql:
            sql.execute("CREATE TABLE future_records (value TEXT)")
            sql.execute("INSERT INTO future_records VALUES ('keep this record')")
            sql.execute(f"PRAGMA user_version = {self.version}")
            sql.execute(
                "INSERT INTO schema_migrations VALUES (?, '2026-10-14', 'future')",
                (self.version,),
            )

    def tearDown(self):
        self.temporary.cleanup()

    def reset(self, **kwargs):
        replace_newer_database(
            self.database, self.backup, expected_version=self.version, **kwargs
        )

    def assert_original(self, path=None):
        with closing(sqlite3.connect(path or self.database)) as sql:
            self.assertEqual(sql.execute("PRAGMA user_version").fetchone()[0], self.version)
            self.assertEqual(sql.execute("SELECT value FROM future_records").fetchone()[0],
                             "keep this record")
            self.assertEqual(sql.execute("SELECT COUNT(*) FROM months").fetchone()[0], 1)

    def test_newer_version_error_exposes_both_versions(self):
        with self.assertRaises(DatabaseVersionTooNew) as raised:
            SQLiteRepository(self.database)
        self.assertEqual(raised.exception.database_version, self.version)
        self.assertEqual(raised.exception.supported_version, SCHEMA_VERSION)
        self.assert_original()

    def test_reset_saves_future_schema_and_records_and_creates_empty_current_database(self):
        self.reset(default_workday_minutes=420)
        self.assert_original(self.backup)
        repository = SQLiteRepository(self.database)
        try:
            self.assertIsNone(repository.load_month(2024, 2))
            month = repository.get_or_create_month(2024, 3)
            self.assertEqual(month.days[0].expected_work_minutes, 420)
        finally:
            repository.close()
        self.assertEqual(list(self.root.glob(".*.replacement.*")), [])

    def test_backup_failure_preserves_original(self):
        with patch("znactime.storage.sqlite.bootstrap.backup_connection",
                   side_effect=StorageUnavailable("disk full")):
            with self.assertRaises(StorageUnavailable):
                self.reset()
        self.assert_original()
        self.assertFalse(self.backup.exists())

    def test_replacement_failure_keeps_original_and_completed_backup(self):
        with patch("znactime.storage.sqlite.bootstrap.publish_staged_file",
                   side_effect=OSError("replacement denied")):
            with self.assertRaises(OSError):
                self.reset()
        self.assert_original()
        self.assert_original(self.backup)
        self.assertEqual(list(self.root.glob(".*.replacement.*")), [])

    def test_cancellation_after_backup_keeps_original_and_backup(self):
        cancel = False

        def progress(phase, _completed, _total):
            nonlocal cancel
            if phase == "Creating empty database":
                cancel = True

        with self.assertRaises(LegacyImportCancelled):
            self.reset(progress=progress, cancelled=lambda: cancel)
        self.assert_original()
        self.assert_original(self.backup)

    def test_cancel_before_backup_preserves_original_without_backup(self):
        with self.assertRaises(LegacyImportCancelled):
            self.reset(cancelled=lambda: True)
        self.assert_original()
        self.assertFalse(self.backup.exists())

    def test_changed_version_prevents_reset(self):
        with self.assertRaises(StorageConflict):
            replace_newer_database(self.database, self.backup, expected_version=self.version + 1)
        self.assert_original()
        self.assertFalse(self.backup.exists())

    def test_backup_destination_cannot_alias_database_or_operational_files(self):
        alias = self.root / "alias.db"
        os.link(self.database, alias)
        for path in (self.database, alias, Path(str(self.database) + "-wal")):
            with self.subTest(path=path), self.assertRaises(StorageConflict):
                replace_newer_database(self.database, path, expected_version=self.version,
                                       overwrite_backup=True)
            self.assert_original()

    def test_existing_backup_is_not_overwritten_without_permission(self):
        self.backup.parent.mkdir()
        self.backup.write_bytes(b"another backup")
        with self.assertRaises(StorageConflict):
            self.reset()
        self.assertEqual(self.backup.read_bytes(), b"another backup")
        self.assert_original()

    def test_backup_includes_committed_wal_records(self):
        source = sqlite3.connect(self.database, isolation_level=None)
        try:
            source.execute("PRAGMA journal_mode = WAL")
            source.execute("PRAGMA wal_autocheckpoint = 0")
            source.execute("INSERT INTO future_records VALUES ('record in WAL')")
            reader = sqlite3.connect(f"{self.database.as_uri()}?mode=ro", uri=True)
            try:
                backup_connection(reader, self.database, self.backup)
            finally:
                reader.close()
            with closing(sqlite3.connect(self.backup)) as copied:
                self.assertEqual(copied.execute("SELECT value FROM future_records").fetchall(),
                                 [("keep this record",), ("record in WAL",)])
        finally:
            source.close()

    def test_external_write_during_backup_aborts_replacement(self):
        written = False

        def progress(phase, _completed, _total):
            nonlocal written
            if phase == "Creating empty database" and not written:
                written = True
                with closing(sqlite3.connect(self.database)) as sql, sql:
                    sql.execute("INSERT INTO future_records VALUES ('concurrent record')")

        with self.assertRaises(StorageConflict):
            self.reset(progress=progress)
        self.assert_original()
        with closing(sqlite3.connect(self.database)) as sql, sql:
            self.assertEqual(sql.execute("SELECT COUNT(*) FROM future_records").fetchone()[0], 2)

    def test_dialog_explains_versions_update_and_backup_and_defaults_to_exit(self):
        dialog = Mock()
        buttons = {}

        def button(label, _parent):
            buttons[label] = Mock(name=label)
            return buttons[label]

        dialog.clickedButton.return_value = None
        with patch("znactime.ui.qt.first_launch.QMessageBox", return_value=dialog), \
             patch("znactime.ui.qt.first_launch.QPushButton", side_effect=button):
            choice = _show_newer_database_dialog(
                None, self.database, DatabaseVersionTooNew(self.version, SCHEMA_VERSION)
            )
        self.assertIs(choice, NewerDatabaseChoice.EXIT)
        dialog.setWindowTitle.assert_called_once_with("Database needs a newer app")
        text = dialog.setInformativeText.call_args.args[0]
        self.assertIn(f"version {self.version}", text)
        self.assertIn(f"version {SCHEMA_VERSION}", text)
        self.assertIn("Update znacTime", text)
        self.assertIn("backup only", text)
        dialog.setDefaultButton.assert_called_once_with(buttons["Exit to update app"])
        dialog.setEscapeButton.assert_called_once_with(buttons["Exit to update app"])

    def test_cancel_save_dialog_does_not_replace_database(self):
        with patch("znactime.ui.qt.first_launch._show_newer_database_dialog",
                   side_effect=[NewerDatabaseChoice.CREATE, NewerDatabaseChoice.EXIT]), \
             patch("znactime.ui.qt.first_launch.QFileDialog.getSaveFileName",
                   return_value=("", "")), \
             patch("znactime.ui.qt.first_launch.replace_newer_database") as replace:
            self.assertIsNone(open_or_initialize_repository(target=self.database))
        replace.assert_not_called()
        self.assert_original()

    def test_declining_confirmation_does_not_replace_database(self):
        with patch("znactime.ui.qt.first_launch._show_newer_database_dialog",
                   side_effect=[NewerDatabaseChoice.CREATE, NewerDatabaseChoice.EXIT]), \
             patch("znactime.ui.qt.first_launch.QFileDialog.getSaveFileName",
                   return_value=(str(self.backup), "")), \
             patch("znactime.ui.qt.first_launch.QMessageBox.question", return_value=0), \
             patch("znactime.ui.qt.first_launch.replace_newer_database") as replace:
            self.assertIsNone(open_or_initialize_repository(target=self.database))
        replace.assert_not_called()
        self.assert_original()

    def test_confirmed_dialog_flow_opens_new_database(self):
        from PySide6.QtWidgets import QMessageBox

        def run_task(_parent, _title, task):
            return task(progress=None, cancelled=None)

        with patch("znactime.ui.qt.first_launch._show_newer_database_dialog",
                   return_value=NewerDatabaseChoice.CREATE), \
             patch("znactime.ui.qt.first_launch.QFileDialog.getSaveFileName",
                   return_value=(str(self.backup), "")), \
             patch("znactime.ui.qt.first_launch.QMessageBox.question",
                   return_value=QMessageBox.StandardButton.Yes), \
             patch("znactime.ui.qt.first_launch.QMessageBox.information"), \
             patch("znactime.ui.qt.first_launch.run_background_task", side_effect=run_task):
            repository = open_or_initialize_repository(target=self.database)
        try:
            self.assertIsNone(repository.load_month(2024, 2))
        finally:
            repository.close()
        self.assert_original(self.backup)


    def test_backup_error_in_dialog_preserves_database_and_allows_exit(self):
        from PySide6.QtWidgets import QMessageBox

        with patch("znactime.ui.qt.first_launch._show_newer_database_dialog",
                   side_effect=[NewerDatabaseChoice.CREATE, NewerDatabaseChoice.EXIT]), \
             patch("znactime.ui.qt.first_launch.QFileDialog.getSaveFileName",
                   return_value=(str(self.backup), "")), \
             patch("znactime.ui.qt.first_launch.QMessageBox.question",
                   return_value=QMessageBox.StandardButton.Yes), \
             patch("znactime.ui.qt.first_launch.QMessageBox.critical") as critical, \
             patch("znactime.ui.qt.first_launch.run_background_task",
                   side_effect=StorageUnavailable("disk full")):
            self.assertIsNone(open_or_initialize_repository(target=self.database))
        self.assert_original()
        self.assertIn("has not been replaced", critical.call_args.args[2])
        self.assertIn("disk full", critical.call_args.args[2])


if __name__ == "__main__":
    unittest.main()
