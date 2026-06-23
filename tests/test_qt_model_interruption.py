import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from znactime.core.models import DayEntry
from znactime.ui.qt import QApplication, QDialog, Qt
from znactime.ui.qt.model import MonthTableModel


class QtModelInterruptionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_model(self):
        model = MonthTableModel()
        model.set_entries(
            [
                DayEntry(
                    cw="",
                    date="17.06.2024",
                    special="Normal day",
                    start="08:00",
                    end="17:00",
                    interruption="01:00",
                )
            ]
        )
        return model

    def test_periods_inside_workday_are_saved_without_override_dialog(self):
        model = self.make_model()

        changed = model.setData(
            model.index(0, 5),
            "12:30-13:00;14:00-14:30",
            Qt.ItemDataRole.EditRole,
        )

        self.assertTrue(changed)
        self.assertEqual(
            model.entries()[0].interruption,
            "12:30-13:00;14:00-14:30",
        )

    @patch(
        "znactime.ui.qt.model.InterruptionBoundaryDialog.selected_overrides",
        return_value=(True, True),
    )
    @patch(
        "znactime.ui.qt.model.InterruptionBoundaryDialog.exec",
        return_value=QDialog.DialogCode.Accepted,
    )
    def test_periods_can_override_both_workday_boundaries(
        self,
        _exec,
        _selected_overrides,
    ):
        model = self.make_model()

        changed = model.setData(
            model.index(0, 5),
            "07:30-08:00;16:30-18:00",
            Qt.ItemDataRole.EditRole,
        )

        self.assertTrue(changed)
        entry = model.entries()[0]
        self.assertEqual(entry.start, "07:30")
        self.assertEqual(entry.end, "18:00")
        self.assertEqual(
            entry.interruption,
            "07:30-08:00;16:30-18:00",
        )

    @patch(
        "znactime.ui.qt.model.InterruptionBoundaryDialog.selected_overrides",
        return_value=(False, False),
    )
    @patch(
        "znactime.ui.qt.model.InterruptionBoundaryDialog.exec",
        return_value=QDialog.DialogCode.Accepted,
    )
    def test_periods_outside_workday_are_rejected_without_override(
        self,
        _exec,
        _selected_overrides,
    ):
        model = self.make_model()

        changed = model.setData(
            model.index(0, 5),
            "07:30-08:00",
            Qt.ItemDataRole.EditRole,
        )

        self.assertFalse(changed)
        self.assertEqual(model.entries()[0].start, "08:00")
        self.assertEqual(model.entries()[0].interruption, "01:00")


if __name__ == "__main__":
    unittest.main()
