import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from znactime.storage.sqlite.bootstrap import (
    BootstrapInspection,
    BootstrapState,
    InterruptedSetupAssessment,
)
from znactime.storage.sqlite.repository import SQLiteRepository
from znactime.ui.qt.first_launch import (
    InterruptedSetupChoice,
    InterruptedSetupResult,
    _resolve_interrupted_setup,
    _show_interrupted_setup_dialog,
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


if __name__ == "__main__":
    unittest.main()
