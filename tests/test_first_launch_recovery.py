import os
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from znactime.storage.sqlite.bootstrap import (
    BootstrapInspection,
    BootstrapState,
    FailedMigrationRecovery,
    InterruptedSetupAssessment,
)
from znactime.storage.errors import StorageCorrupt
from znactime.storage.sqlite.repository import SQLiteRepository
from znactime.ui.qt.first_launch import (
    FailedMigrationChoice,
    InterruptedSetupChoice,
    InterruptedSetupResult,
    _show_failed_migration_dialog,
    _resolve_interrupted_setup,
    _show_import_complete,
    _show_interrupted_setup_dialog,
    open_or_initialize_repository,
)


class FirstLaunchRecoveryDialogTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary.name) / "znactime.db"

    def tearDown(self):
        self.temporary.cleanup()

    def _assessment(self, state, recoverable):
        target = Path("znactime.db")
        suffix = ".creating" if state is BootstrapState.INTERRUPTED_CREATE else ".migrating"
        return InterruptedSetupAssessment(
            BootstrapInspection(state, target, target.with_name(target.name + suffix)),
            recoverable,
            "validation detail",
        )

    def _show_and_select(self, assessment, selected_label):
        dialog = Mock()
        buttons = {}

        def create_button(label, _parent):
            button = Mock(name=label)
            buttons[label] = button
            return button

        def select_button():
            dialog.clickedButton.return_value = buttons[selected_label]

        dialog.exec.side_effect = select_button
        with (
            patch("znactime.ui.qt.first_launch.QMessageBox", return_value=dialog),
            patch(
                "znactime.ui.qt.first_launch.QPushButton",
                side_effect=create_button,
            ),
        ):
            choice = _show_interrupted_setup_dialog(None, assessment)
        return choice, dialog, buttons

    def test_valid_new_database_offers_finish_archive_and_exit(self):
        choice, dialog, buttons = self._show_and_select(
            self._assessment(BootstrapState.INTERRUPTED_CREATE, True),
            "Finish setup",
        )

        self.assertEqual(choice, InterruptedSetupChoice.RECOVER)
        self.assertEqual(
            set(buttons),
            {"Finish setup", "Archive and start over", "Exit application"},
        )
        dialog.setDefaultButton.assert_called_once_with(buttons["Finish setup"])
        dialog.setEscapeButton.assert_called_once_with(buttons["Exit application"])

    def test_valid_staging_choice_recovers_repository(self):
        staging = self.database.with_name(self.database.name + ".creating")
        repository = SQLiteRepository.create(staging)
        repository.close()

        with patch(
            "znactime.ui.qt.first_launch._show_interrupted_setup_dialog",
            return_value=InterruptedSetupChoice.RECOVER,
        ):
            result, recovered = _resolve_interrupted_setup(None, self.database)

        self.assertEqual(result, InterruptedSetupResult.RECOVERED)
        self.assertTrue(self.database.exists())
        self.assertFalse(staging.exists())
        recovered.close()

    @patch("znactime.ui.qt.first_launch.QMessageBox.information")
    def test_invalid_staging_choice_archives_and_restarts(self, information):
        staging = self.database.with_name(self.database.name + ".migrating")
        original = b"interrupted import"
        staging.write_bytes(original)

        with patch(
            "znactime.ui.qt.first_launch._show_interrupted_setup_dialog",
            return_value=InterruptedSetupChoice.ARCHIVE,
        ):
            result, repository = _resolve_interrupted_setup(None, self.database)

        self.assertEqual(result, InterruptedSetupResult.RETRY)
        self.assertIsNone(repository)
        self.assertFalse(staging.exists())
        archive = next((self.database.parent / "recovery").iterdir())
        self.assertEqual((archive / staging.name).read_bytes(), original)
        information.assert_called_once()

    def test_exit_preserves_valid_staging_byte_for_byte(self):
        staging = self.database.with_name(self.database.name + ".creating")
        repository = SQLiteRepository.create(staging)
        repository.close()
        original = staging.read_bytes()

        with patch(
            "znactime.ui.qt.first_launch._show_interrupted_setup_dialog",
            return_value=InterruptedSetupChoice.EXIT,
        ):
            result, repository = _resolve_interrupted_setup(None, self.database)

        self.assertEqual(result, InterruptedSetupResult.EXIT)
        self.assertIsNone(repository)
        self.assertFalse(self.database.exists())
        self.assertEqual(staging.read_bytes(), original)

    def test_incomplete_import_offers_only_archive_and_exit(self):
        choice, dialog, buttons = self._show_and_select(
            self._assessment(BootstrapState.INTERRUPTED_MIGRATION, False),
            "Archive and restart import",
        )

        self.assertEqual(choice, InterruptedSetupChoice.ARCHIVE)
        self.assertEqual(
            set(buttons),
            {"Archive and restart import", "Exit application"},
        )
        dialog.setDefaultButton.assert_called_once_with(
            buttons["Archive and restart import"]
        )
        dialog.setEscapeButton.assert_called_once_with(buttons["Exit application"])

    def test_import_completion_dialog_contains_clickable_log_link(self):
        log_path = self.database.parent / "import-logs" / "completed.log"
        preflight = Mock(
            source_root=self.database.parent / "legacy data",
            months=(Mock(days=(object(), object())),),
        )
        dialog = Mock()
        label = Mock()
        dialog.findChildren.return_value = [label]

        with patch(
            "znactime.ui.qt.first_launch.QMessageBox",
            return_value=dialog,
        ):
            _show_import_complete(None, preflight, log_path)

        informative = dialog.setInformativeText.call_args.args[0]
        self.assertIn("Open detailed import log", informative)
        self.assertIn("file:///", informative)
        self.assertIn("completed.log", informative)
        dialog.setTextInteractionFlags.assert_called_once()
        label.setOpenExternalLinks.assert_called_once_with(True)
        dialog.exec.assert_called_once()

    def test_failed_migration_dialog_offers_recover_or_exit(self):
        dialog = Mock()
        buttons = {}

        def create_button(label, _parent):
            button = Mock(name=label)
            buttons[label] = button
            return button

        def select_recovery():
            dialog.clickedButton.return_value = buttons["Recover database"]

        error = StorageCorrupt("schema mismatch")
        error.recovery_backup_path = self.database.parent / "recovery" / "backup.db"
        dialog.exec.side_effect = select_recovery
        with (
            patch("znactime.ui.qt.first_launch.QMessageBox", return_value=dialog),
            patch(
                "znactime.ui.qt.first_launch.QPushButton",
                side_effect=create_button,
            ),
        ):
            choice = _show_failed_migration_dialog(None, self.database, error)

        self.assertEqual(choice, FailedMigrationChoice.RECOVER)
        self.assertEqual(set(buttons), {"Recover database", "Exit application"})
        dialog.setDefaultButton.assert_called_once_with(buttons["Recover database"])
        dialog.setEscapeButton.assert_called_once_with(buttons["Exit application"])

    def test_pending_failed_migration_recovery_resumes_upgrade_and_opens(self):
        recovery = FailedMigrationRecovery(
            self.database.parent / "recovery" / "backup.db",
            "signature",
            "2026-09-04T08:00:00Z",
            "schema mismatch",
        )
        inspection = BootstrapInspection(BootstrapState.READY, self.database)
        recovered_repository = Mock(spec=SQLiteRepository)
        with (
            patch("znactime.ui.qt.first_launch.database_path", return_value=self.database),
            patch("znactime.ui.qt.first_launch.inspect_bootstrap", return_value=inspection),
            patch(
                "znactime.ui.qt.first_launch.failed_migration_recovery",
                return_value=recovery,
            ),
            patch("znactime.ui.qt.first_launch.startup_lock", return_value=nullcontext()),
            patch(
                "znactime.ui.qt.first_launch.recover_failed_schema_migration",
                return_value=recovered_repository,
            ) as recover,
            patch("znactime.ui.qt.first_launch.SQLiteRepository") as repository,
        ):
            opened = open_or_initialize_repository()

        self.assertIs(opened, recovered_repository)
        repository.assert_not_called()
        recover.assert_called_once_with(
            self.database,
            recovery.backup_path,
            recovery.failure,
        )

    def test_failed_migration_recovery_action_upgrades_and_opens(self):
        backup = self.database.parent / "recovery" / "schema-v4" / self.database.name
        error = StorageCorrupt("schema mismatch")
        error.recovery_backup_path = backup
        recovered = Mock(spec=SQLiteRepository)
        inspection = BootstrapInspection(BootstrapState.READY, self.database)
        with (
            patch("znactime.ui.qt.first_launch.database_path", return_value=self.database),
            patch("znactime.ui.qt.first_launch.inspect_bootstrap", return_value=inspection),
            patch("znactime.ui.qt.first_launch.failed_migration_recovery", return_value=None),
            patch("znactime.ui.qt.first_launch.SQLiteRepository", side_effect=error),
            patch(
                "znactime.ui.qt.first_launch._show_failed_migration_dialog",
                return_value=FailedMigrationChoice.RECOVER,
            ),
            patch("znactime.ui.qt.first_launch.startup_lock", return_value=nullcontext()),
            patch(
                "znactime.ui.qt.first_launch.recover_failed_schema_migration",
                return_value=recovered,
            ) as recover,
        ):
            opened = open_or_initialize_repository()

        self.assertIs(opened, recovered)
        recover.assert_called_once_with(self.database, backup, str(error))


if __name__ == "__main__":
    unittest.main()
