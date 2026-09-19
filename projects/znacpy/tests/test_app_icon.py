import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from znactime.ui.qt import QApplication, QIcon
from znactime.__main__ import (
    APP_USER_MODEL_ID,
    _set_windows_app_user_model_id,
    _show_already_running_dialog,
    main,
)
from znactime.storage.errors import ApplicationAlreadyRunning
from znactime.ui.qt.app import APP_ICON_PATH


class AppIconTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_bundled_app_icon_is_readable(self):
        self.assertTrue(APP_ICON_PATH.is_file())
        self.assertFalse(QIcon(str(APP_ICON_PATH)).isNull())

    def test_windows_app_identity_is_set_for_taskbar_grouping(self):
        shell32 = SimpleNamespace(
            SetCurrentProcessExplicitAppUserModelID=Mock(return_value=0)
        )

        with (
            patch("znactime.__main__.sys.platform", "win32"),
            patch(
                "znactime.__main__.ctypes.windll",
                SimpleNamespace(shell32=shell32),
            ),
        ):
            configured = _set_windows_app_user_model_id()

        self.assertTrue(configured)
        shell32.SetCurrentProcessExplicitAppUserModelID.assert_called_once_with(
            APP_USER_MODEL_ID
        )

    @patch("znactime.__main__.QMessageBox")
    def test_already_running_dialog_has_only_an_exit_action(self, message_box):
        dialog = message_box.return_value
        exit_button = dialog.addButton.return_value

        _show_already_running_dialog()

        dialog.setWindowTitle.assert_called_once_with("znacTime is already running")
        dialog.addButton.assert_called_once_with(
            "Exit application",
            message_box.ButtonRole.RejectRole,
        )
        dialog.setDefaultButton.assert_called_once_with(exit_button)
        dialog.setEscapeButton.assert_called_once_with(exit_button)
        dialog.exec.assert_called_once_with()

    def test_second_instance_exits_before_repository_or_window_construction(self):
        application = Mock()
        database = Path("already-running.db")
        with (
            patch("znactime.__main__.QApplication", return_value=application),
            patch("znactime.__main__.database_path", return_value=database),
            patch(
                "znactime.__main__.application_lock",
                side_effect=ApplicationAlreadyRunning("already running"),
            ),
            patch("znactime.__main__._show_already_running_dialog") as notification,
            patch("znactime.__main__.open_or_initialize_repository") as open_repository,
            patch("znactime.__main__.TimeTrackerApp") as window_type,
        ):
            result = main()

        self.assertEqual(result, 0)
        notification.assert_called_once_with()
        open_repository.assert_not_called()
        window_type.assert_not_called()
        application.exec.assert_not_called()


if __name__ == "__main__":
    unittest.main()
