import os
import re
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest

from znactime.ui.qt import QApplication, QFont, QPalette, QPushButton, Qt
from znactime.ui.qt.app import TimeTrackerApp
from znactime.ui.qt.header import HeaderWidget
from znactime.ui.qt.color_scheme import theme_color


class QtHeaderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_closed_month_uses_red_lock_without_redundant_closed_text(self):
        header = HeaderWidget()

        for dark in (False, True):
            with self.subTest(dark=dark):
                with patch("znactime.ui.qt.header.is_dark_theme", return_value=dark):
                    header.apply_theme()
                    header.set_overtime_text("This Month: 01:30", closed=True)
                self.assertEqual(header.overtime_label.text(), "This Month: 01:30")
                self.assertEqual(header.month_status_label.text(), "")
                self.assertTrue(header.month_status_label.isHidden())
                self.assertEqual(header.month_lock_icon.accessibleName(), "Month closed")
                image = header.month_lock_icon.pixmap().toImage()
                solid_colors = {
                    image.pixelColor(x, y).name()
                    for x in range(image.width()) for y in range(image.height())
                    if image.pixelColor(x, y).alpha() == 255
                }
                self.assertIn(theme_color("tokens.danger_text", dark=dark), solid_colors)

    def test_closed_month_discontinuity_is_visible_in_overtime_badge(self):
        header = HeaderWidget()

        header.set_overtime_text(
            "This Month: 01:00",
            closed=True,
            carry_discontinuity=True,
        )

        self.assertIn("carry-over discontinuity", header.month_status_label.text())
        self.assertFalse(header.month_status_label.isHidden())
        self.assertIn("saved carry-over no longer matches", header.overtime_button.toolTip())

    def test_overtime_button_updates_lock_icons_tooltips_and_keyboard_action(self):
        header = HeaderWidget()
        self.addCleanup(header.close)
        clicked = Mock()
        header.monthActionClicked.connect(clicked)
        header.set_overtime_text("This Month: 02:15")
        header.show()
        self.app.processEvents()

        self.assertIsInstance(header.overtime_button, QPushButton)
        self.assertEqual(header.month_lock_icon.accessibleName(), "Month open")
        self.assertIn("Click to review and close", header.overtime_button.toolTip())
        self.assertTrue(header.month_status_label.isHidden())
        for label in (header.overtime_label, header.month_lock_icon):
            self.assertTrue(header.overtime_button.rect().contains(label.geometry()))
        unlocked = header.month_lock_icon.pixmap().toImage()
        QTest.mouseClick(header.overtime_button, Qt.MouseButton.LeftButton)
        clicked.assert_called_once_with()

        header.set_overtime_text("This Month: 02:15", closed=True)
        self.app.processEvents()
        self.assertEqual(header.month_lock_icon.accessibleName(), "Month closed")
        self.assertNotEqual(header.month_lock_icon.pixmap().toImage(), unlocked)
        self.assertIn("read-only", header.overtime_button.toolTip())
        self.assertIn("Click to reopen", header.overtime_button.toolTip())
        self.assertIn("Reopen this month", header.overtime_button.accessibleName())
        self.assertEqual(header.overtime_button.height(), header.period_widget.height())
        self.assertTrue(header.month_status_label.isHidden())
        for label in (header.overtime_label, header.month_lock_icon):
            self.assertTrue(header.overtime_button.rect().contains(label.geometry()))
        clicked.reset_mock()
        header.overtime_button.setFocus()
        QTest.keyClick(header.overtime_button, Qt.Key.Key_Space)
        clicked.assert_called_once_with()

        header.set_overtime_text("This Month: 02:15")
        self.assertEqual(header.month_lock_icon.pixmap().toImage(), unlocked)
        self.assertTrue(header.month_status_label.isHidden())

    def test_unclosed_last_month_is_red_with_hint_only_on_the_info_icon(self):
        header = HeaderWidget()
        self.addCleanup(header.close)
        header.set_carry_over_text("Last Month: 00:00", previous_month_unclosed=True)
        with patch("znactime.ui.qt.header.overtime_text_color_hex", return_value="#ff0000"):
            header.apply_theme()
        header.show()
        self.app.processEvents()
        label = header.carry_over_label
        info = header.carry_over_info

        self.assertEqual(label.text(), "Last month is not closed")
        self.assertEqual(label.palette().color(QPalette.ColorRole.WindowText).name(), "#ff0000")
        self.assertEqual(label.toolTip(), "")
        self.assertTrue(info.isVisible())
        self.assertFalse(info.icon().isNull())
        self.assertEqual(info.toolTip(), "Close last month to carry its time balance over to this month.")
        with patch("znactime.ui.qt.header.QToolTip.showText") as show_tooltip:
            QTest.mouseClick(label, Qt.MouseButton.LeftButton)
            show_tooltip.assert_not_called()
            QTest.mouseClick(info, Qt.MouseButton.LeftButton)
            self.assertEqual(show_tooltip.call_args.args[1], info.toolTip())
            show_tooltip.reset_mock()
            QTest.keyClick(info, Qt.Key.Key_Space)
            self.assertEqual(show_tooltip.call_args.args[1], info.toolTip())

        header.set_carry_over_text("Last Month: 01:30")
        self.assertEqual(label.text(), "Last Month: 01:30")
        self.assertFalse(label.property("unclosed"))
        self.assertEqual(label.toolTip(), "")
        self.assertEqual(info.toolTip(), "")
        self.assertFalse(info.isVisible())
        with patch("znactime.ui.qt.header.QToolTip.showText") as show_tooltip:
            QTest.mouseClick(label, Qt.MouseButton.LeftButton)
            show_tooltip.assert_not_called()

    def test_today_button_returns_to_the_current_month_with_one_reload(self):
        header = HeaderWidget()
        self.addCleanup(header.close)
        header.set_period(2024, 12)
        window = SimpleNamespace(
            header=header, load_month=Mock(),
            table=SimpleNamespace(view=SimpleNamespace(ensure_today_visible=Mock())),
        )
        header.selectionChanged.connect(window.load_month)
        header.todayClicked.connect(lambda: TimeTrackerApp.show_today(window))
        header.show()
        self.app.processEvents()

        with patch("znactime.ui.qt.app.datetime") as clock:
            clock.now.return_value = datetime(2025, 1, 12)
            QTest.mouseClick(header.today_button, Qt.MouseButton.LeftButton)

        self.assertEqual((header.year(), header.month()), (2025, 1))
        window.load_month.assert_called_once_with()
        window.table.view.ensure_today_visible.assert_called_once_with()

    def test_period_controls_use_generated_theme_chevrons(self):
        header = HeaderWidget()
        asset_paths = re.findall(
            r'image: url\("([^\"]+chevron_(?:up|down)_[^\"]+\.png)"\)',
            header.styleSheet(),
        )

        self.assertEqual(len(asset_paths), 6)
        self.assertEqual(len(set(asset_paths)), 4)
        self.assertTrue(any("on_primary" in path for path in asset_paths))
        self.assertTrue(all(Path(path).is_file() for path in asset_paths))

    def test_four_year_digits_fit_with_room_for_the_caret_at_different_font_sizes(self):
        header = HeaderWidget()
        self.addCleanup(header.close)

        for point_size in (8, 10, 12, 14):
            with self.subTest(point_size=point_size):
                font = QFont(self.app.font())
                font.setPointSize(point_size)
                header.setFont(font)
                header.apply_theme()
                header.set_period(2026, 9)
                header.resize(1000, header.sizeHint().height())
                header.show()
                self.app.processEvents()
                editor = header.year_box.lineEdit()
                margins = editor.textMargins()
                available_width = (
                    editor.contentsRect().width() - margins.left() - margins.right()
                )
                widest_year = max(
                    editor.fontMetrics().horizontalAdvance(str(year))
                    for year in range(2000, 2101)
                )

                self.assertGreaterEqual(available_width, widest_year + 8)

    def test_app_passes_month_closed_state_to_overtime_badge(self):
        app = SimpleNamespace(
            current_overtime=0.0,
            month_closed=True,
            header=SimpleNamespace(set_overtime_text=Mock()),
        )

        TimeTrackerApp.set_current_overtime(app, 1.5)

        app.header.set_overtime_text.assert_called_once_with(
            "This Month: 01:30",
            closed=True,
            carry_discontinuity=False,
        )


if __name__ == "__main__":
    unittest.main()
