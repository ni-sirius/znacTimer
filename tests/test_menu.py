import os
import unittest
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from znactime.ui.qt import QApplication
from znactime.ui.qt.menu import MenuBar


class MenuBarTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _action_texts(menu):
        return [action.text() for action in menu.actions() if not action.isSeparator()]

    def test_data_operations_are_in_separate_data_menu(self):
        menu = MenuBar(
            None,
            close_month_command=Mock(),
            appearance_command=Mock(),
            work_schedule_command=Mock(),
            about_command=Mock(),
            export_month_command=Mock(),
            export_pdf_command=Mock(),
            backup_command=Mock(),
            import_csv_command=Mock(),
        )
        top_level = [action.text() for action in menu.actions()]

        self.assertEqual(top_level, ["Month", "Data", "Settings", "Help"])
        self.assertEqual(
            self._action_texts(menu.month_menu),
            ["Close Month", "Exit"],
        )
        self.assertEqual(
            self._action_texts(menu.data_menu),
            [
                "Import CSV Data...",
                "Export Month CSV",
                "Export PDF",
                "Back Up Database",
            ],
        )

    def test_reopen_action_is_available_only_for_closed_month(self):
        reopen = Mock()
        menu = MenuBar(
            None,
            close_month_command=Mock(),
            appearance_command=Mock(),
            work_schedule_command=Mock(),
            about_command=Mock(),
            reopen_month_command=reopen,
        )

        self.assertFalse(menu.reopen_month_action.isEnabled())
        menu.set_month_closed(True)
        self.assertTrue(menu.reopen_month_action.isEnabled())
        self.assertFalse(menu.close_month_action.isEnabled())
        menu.reopen_month_action.trigger()
        reopen.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
