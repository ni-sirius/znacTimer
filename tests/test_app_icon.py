import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from znactime.ui.qt import QApplication, QIcon
from znactime.__main__ import APP_USER_MODEL_ID, _set_windows_app_user_model_id
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


if __name__ == "__main__":
    unittest.main()
