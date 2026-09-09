import os
import inspect
import unittest
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from znactime.config import APP_NAME
from znactime.ui.qt import QApplication, QKeySequence
from znactime.ui.qt.menu import MenuBar


class MenuBarTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _action_texts(menu):
        return [action.text() for action in menu.actions() if not action.isSeparator()]

    def test_data_operations_are_in_separate_data_menu(self):
        export_month = Mock()
        export_pdf = Mock()
        backup = Mock()
        import_csv = Mock()
        exit_app = Mock()
        menu = MenuBar(
            None,
            close_month_command=Mock(),
            appearance_command=Mock(),
            work_schedule_command=Mock(),
            about_command=Mock(),
            export_month_command=export_month,
            export_pdf_command=export_pdf,
            backup_command=backup,
            import_csv_command=import_csv,
            exit_command=exit_app,
        )
        top_level = [action.text() for action in menu.actions()]

        self.assertEqual(top_level, ["&Data", "&Month", "&Settings", "&Help"])
        self.assertEqual(
            self._action_texts(menu.month_menu),
            ["&Close Month"],
        )
        self.assertEqual(
            self._action_texts(menu.data_menu),
            [
                "&Import CSV Data...",
                "Export Month &CSV",
                "Export &PDF",
                "&Back Up Database",
                "E&xit",
            ],
        )
        self.assertEqual(menu.data_menu.actions()[-1].text(), "E&xit")

        for action in menu.data_menu.actions():
            if not action.isSeparator():
                action.trigger()
        import_csv.assert_called_once_with()
        export_month.assert_called_once_with()
        export_pdf.assert_called_once_with()
        backup.assert_called_once_with()
        exit_app.assert_called_once_with()

    def test_menu_mnemonics_and_platform_quit_shortcut(self):
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
            exit_command=Mock(),
            reopen_month_command=Mock(),
        )

        self.assertEqual(
            [action.text() for action in menu.actions()],
            ["&Data", "&Month", "&Settings", "&Help"],
        )
        self.assertEqual(
            self._action_texts(menu.data_menu),
            [
                "&Import CSV Data...",
                "Export Month &CSV",
                "Export &PDF",
                "&Back Up Database",
                "E&xit",
            ],
        )
        self.assertEqual(
            self._action_texts(menu.month_menu),
            ["&Close Month", "&Reopen Month"],
        )
        self.assertEqual(
            self._action_texts(menu.settings_menu),
            ["&Appearance", "&Work schedule"],
        )
        self.assertEqual(
            self._action_texts(menu.help_menu),
            [f"&About {APP_NAME}"],
        )
        quit_shortcuts = menu.exit_action.shortcuts()
        self.assertIn(QKeySequence("Ctrl+Q"), quit_shortcuts)
        for shortcut in QKeySequence.keyBindings(QKeySequence.StandardKey.Quit):
            self.assertIn(shortcut, quit_shortcuts)

    def test_all_five_data_commands_are_required(self):
        signature = inspect.signature(MenuBar.__init__)

        for name in (
            "import_csv_command",
            "export_month_command",
            "export_pdf_command",
            "backup_command",
            "exit_command",
        ):
            self.assertIs(signature.parameters[name].default, inspect.Parameter.empty)

    def test_reopen_action_is_available_only_for_closed_month(self):
        reopen = Mock()
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
            exit_command=Mock(),
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
