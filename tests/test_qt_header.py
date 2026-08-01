import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from znactime.ui.qt import QApplication
from znactime.ui.qt.app import TimeTrackerApp
from znactime.ui.qt.header import HeaderWidget


class QtHeaderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_closed_month_adds_red_closed_marker_to_overtime_badge(self):
        header = HeaderWidget()

        with patch(
            "znactime.ui.qt.header.overtime_text_color_hex",
            return_value="#ff0000",
        ):
            header.set_overtime_text("Overtime: 01:30", closed=True)

        self.assertIn("Overtime: 01:30", header.overtime_label.text())
        self.assertIn(
            '<span style="color: #ff0000;">Closed</span>',
            header.overtime_label.text(),
        )

    def test_app_passes_month_closed_state_to_overtime_badge(self):
        app = SimpleNamespace(
            current_overtime=0.0,
            month_closed=True,
            header=SimpleNamespace(set_overtime_text=Mock()),
        )

        TimeTrackerApp.set_current_overtime(app, 1.5)

        app.header.set_overtime_text.assert_called_once_with(
            "Overtime: 01:30",
            closed=True,
        )


if __name__ == "__main__":
    unittest.main()
