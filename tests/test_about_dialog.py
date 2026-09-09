import os
import unittest
from pathlib import Path
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from znactime.config import VERSION
from znactime.ui.qt import QApplication
from znactime.ui.qt.app import (
    ABOUT_CONTACT,
    ABOUT_LICENSE,
    ABOUT_USE,
    ABOUT_WEBSITE,
    PYSIDE_VERSION,
    create_about_dialog,
)
from znactime.ui.qt.menu import MenuBar


class AboutDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_about_menu_action_opens_about_dialog(self):
        about_command = Mock()
        menu = MenuBar(
            None,
            close_month_command=Mock(),
            appearance_command=Mock(),
            work_schedule_command=Mock(),
            about_command=about_command,
            export_month_command=Mock(),
            export_pdf_command=Mock(),
            backup_command=Mock(),
            import_csv_command=Mock(),
            exit_command=Mock(),
        )

        menu.about_action.trigger()

        about_command.assert_called_once_with()

    def test_about_dialog_contains_product_details_and_icon(self):
        dialog = create_about_dialog()
        text = dialog.text()

        self.assertEqual(dialog.windowTitle(), "About znacTime")
        self.assertIn(VERSION, text)
        self.assertIn(ABOUT_LICENSE, text)
        self.assertIn(PYSIDE_VERSION, text)
        self.assertIn("LGPL v3", text)
        self.assertIn(ABOUT_USE, text)
        self.assertIn(ABOUT_WEBSITE, text)
        self.assertIn(ABOUT_CONTACT, text)
        self.assertFalse(dialog.iconPixmap().isNull())

    def test_repository_contains_mit_license(self):
        license_text = (Path(__file__).parents[1] / "LICENSE").read_text(
            encoding="utf-8"
        )

        self.assertIn("MIT License", license_text)
        self.assertIn("Copyright (c) 2026 znac", license_text)


if __name__ == "__main__":
    unittest.main()
